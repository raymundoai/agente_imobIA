from __future__ import annotations

import logging
import socket
from typing import Any
from uuid import uuid4

from app.container import Container
from app.modules.billing_usage.commercial import CommercialEntitlementService
from app.modules.billing_usage.service import (
    CreditLedgerService,
    chat_charge,
    fixed_credit_charge,
)
from app.modules.capture.connectors import default_connector_registry
from app.modules.capture.federated import (
    FederatedSearchRepository,
    LostCaptureJobLease,
    demand_from_search_snapshot,
)
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository


class CaptureJobProcessor:
    def __init__(self, container: Container, worker_id: str | None = None) -> None:
        self.container = container
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid4()}"
        settings = container.settings
        self.registry = default_connector_registry(
            container.capture_http_client,
            web_discovery_enabled=settings.capture_web_discovery_enabled,
            openai_api_key=(
                settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
            ),
            web_discovery_model=settings.capture_web_discovery_model,
            web_discovery_max_results=settings.capture_web_discovery_max_results,
            web_discovery_max_output_tokens=settings.capture_web_discovery_max_output_tokens,
        )

    def process_next(self) -> dict[str, Any] | None:
        with self.container.database.session_factory() as session:
            job = FederatedSearchRepository(session).claim_next(
                self.container.settings.capture_job_stale_seconds,
                self.worker_id,
            )
        if job is None:
            return None
        self._start_billing(job)
        connector = None
        try:
            with self.container.database.session_factory() as session:
                repository = FederatedSearchRepository(session)
                run = repository.get_run(job.tenant_id, job.search_run_id)
                demand = SqlAlchemyLeadDemandRepository(session).get_by_id(
                    job.tenant_id, job.demand_id
                )
            if run is None or demand is None or run.status == "cancelled":
                return {
                    "id": str(job.id),
                    "source_id": job.source_id,
                    "status": "cancelled",
                }
            demand = demand_from_search_snapshot(demand, run.filters)
            connector = self.registry.get(job.source_id)
            batch = connector.search(demand)
            self._record_provider_usage(job, batch.metadata.get("usage"))
            matched = 0
            record_errors: list[str] = []
            with self.container.database.session_factory() as session:
                repository = FederatedSearchRepository(session)
                for record in batch.records:
                    try:
                        with session.begin_nested():
                            _, is_match = repository.upsert_and_match(job, demand, record)
                            matched += int(is_match)
                    except LostCaptureJobLease:
                        raise
                    except Exception as exc:
                        record_errors.append(str(exc))
                        logging.getLogger(__name__).warning(
                            "Capture record ignored: run=%s source=%s listing=%s error=%s",
                            job.search_run_id,
                            job.source_id,
                            record.source_listing_id,
                            exc,
                        )
                if batch.records and len(record_errors) == len(batch.records):
                    raise RuntimeError(
                        f"Todos os {len(batch.records)} anúncios da fonte falharam na importação: "
                        f"{record_errors[0]}"
                    )
                repository.complete(
                    job,
                    discovered_count=len(batch.records),
                    imported_count=matched,
                    parser_version=batch.parser_version,
                )
            self._finalize_billing(job)
            return {
                "id": str(job.id),
                "source_id": job.source_id,
                "status": "completed",
                "discovered": len(batch.records),
                "matched": matched,
                "ignored": len(record_errors),
            }
        except Exception as exc:
            if connector is not None:
                self._record_provider_usage(job, getattr(connector, "last_usage", None))
            error_code = getattr(exc, "error_code", "capture_failed")
            retryable = bool(getattr(exc, "retryable", True))
            with self.container.database.session_factory() as session:
                status = FederatedSearchRepository(session).fail(
                    job,
                    str(exc),
                    error_code=error_code,
                    retryable=retryable,
                    backoff_seconds=self.container.settings.capture_job_backoff_seconds,
                )
            self._finalize_billing(job)
            return {
                "id": str(job.id),
                "source_id": job.source_id,
                "status": status,
                "error": str(exc),
                "error_code": error_code,
            }

    def _start_billing(self, job: Any) -> None:
        with self.container.database.session_factory() as session:
            run = FederatedSearchRepository(session).get_run(job.tenant_id, job.search_run_id)
            if run is None or not run.billing_reservation_key:
                return
            ledger = CreditLedgerService(session)
            status = ledger.reservation_status(job.tenant_id, run.billing_reservation_key)
            if status in {"reserved", "started"}:
                ledger.start_reservation(job.tenant_id, run.billing_reservation_key)
            CommercialEntitlementService(session).touch(
                job.tenant_id,
                f"commercial:{run.billing_reservation_key}",
                max(self.container.settings.capture_job_stale_seconds * 5, 900),
            )

    def _record_provider_usage(self, job: Any, usage: object) -> None:
        if not isinstance(usage, dict) or not any(int(value or 0) for value in usage.values()):
            return
        with self.container.database.session_factory() as session:
            run = FederatedSearchRepository(session).get_run(job.tenant_id, job.search_run_id)
            if run is None or not run.billing_reservation_key:
                return
            ledger = CreditLedgerService(session)
            extra = ledger.reservation_extra(job.tenant_id, run.billing_reservation_key) or {}
            if int(extra.get("accepted_call_count", 0)) > 0:
                return
            ledger.record_accepted_ai_call(
                job.tenant_id,
                run.billing_reservation_key,
                model=self.container.settings.capture_web_discovery_model,
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                cached_input_tokens=int(usage.get("cached_input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
            )

    def _finalize_billing(self, job: Any) -> None:
        with self.container.database.session_factory() as session:
            run = FederatedSearchRepository(session).get_run(job.tenant_id, job.search_run_id)
            if (
                run is None
                or not run.billing_reservation_key
                or run.status not in {"completed", "partial", "failed", "cancelled"}
            ):
                return
            ledger = CreditLedgerService(session)
            reservation_status = ledger.reservation_status(
                job.tenant_id, run.billing_reservation_key
            )
            if reservation_status in {None, "released", "settled"}:
                self._finalize_commercial_billing(session, run)
                return
            extra = ledger.reservation_extra(job.tenant_id, run.billing_reservation_key) or {}
            accepted_calls = int(extra.get("accepted_call_count", 0))
            is_ai = job.source_id == "web_discovery"
            if run.status in {"failed", "cancelled"} and not (is_ai and accepted_calls):
                ledger.release_reservation(job.tenant_id, run.billing_reservation_key)
                self._finalize_commercial_billing(session, run)
                return
            if is_ai:
                charge = chat_charge(
                    self.container.settings.capture_web_discovery_model,
                    input_tokens=int(extra.get("accepted_input_tokens", 0)),
                    cached_input_tokens=int(extra.get("accepted_cached_input_tokens", 0)),
                    output_tokens=int(extra.get("accepted_output_tokens", 0)),
                )
                model = self.container.settings.capture_web_discovery_model
            else:
                charge = fixed_credit_charge(
                    self.container.settings.capture_standard_search_credits
                )
                model = "federated-standard-v1"
            ledger.settle_reservation(
                job.tenant_id,
                idempotency_key=run.billing_reservation_key,
                charge=charge,
                model=model,
                reference_id=run.id,
                extra={
                    "search_run_id": str(run.id),
                    "source_count": run.source_count,
                    "result_count": run.result_count,
                    "status": run.status,
                },
            )
            session.commit()
            self._finalize_commercial_billing(session, run)

    @staticmethod
    def _finalize_commercial_billing(session: Any, run: Any) -> None:
        if not run.billing_reservation_key:
            return
        key = f"commercial:{run.billing_reservation_key}"
        commercial = CommercialEntitlementService(session)
        if commercial.reservation_status(run.tenant_id, key) in {
            None,
            "released",
            "settled",
        }:
            return
        if run.status in {"completed", "partial"}:
            commercial.settle(
                run.tenant_id,
                key,
                reference_id=run.id,
                extra={
                    "search_run_id": str(run.id),
                    "source_count": run.source_count,
                    "result_count": run.result_count,
                    "status": run.status,
                },
            )
        elif run.status in {"failed", "cancelled"}:
            commercial.release(run.tenant_id, key)
