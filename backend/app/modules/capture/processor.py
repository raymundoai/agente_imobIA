from __future__ import annotations

import socket
from typing import Any
from uuid import uuid4

from app.container import Container
from app.modules.capture.connectors import default_connector_registry
from app.modules.capture.federated import FederatedSearchRepository
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository


class CaptureJobProcessor:
    def __init__(self, container: Container, worker_id: str | None = None) -> None:
        self.container = container
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid4()}"
        self.registry = default_connector_registry(container.http_client)

    def process_next(self) -> dict[str, Any] | None:
        with self.container.database.session_factory() as session:
            job = FederatedSearchRepository(session).claim_next(
                self.container.settings.capture_job_stale_seconds,
                self.worker_id,
            )
        if job is None:
            return None
        try:
            with self.container.database.session_factory() as session:
                demand = SqlAlchemyLeadDemandRepository(session).get_by_id(
                    job.tenant_id, job.demand_id
                )
            if demand is None:
                raise RuntimeError("Lead demand not found")
            connector = self.registry.get(job.source_id)
            batch = connector.search(demand)
            matched = 0
            with self.container.database.session_factory() as session:
                repository = FederatedSearchRepository(session)
                for record in batch.records:
                    _, is_match = repository.upsert_and_match(job, demand, record)
                    matched += int(is_match)
                repository.complete(
                    job,
                    discovered_count=len(batch.records),
                    imported_count=len(batch.records),
                    parser_version=batch.parser_version,
                )
            return {
                "id": str(job.id),
                "source_id": job.source_id,
                "status": "completed",
                "discovered": len(batch.records),
                "matched": matched,
            }
        except Exception as exc:
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
            return {
                "id": str(job.id),
                "source_id": job.source_id,
                "status": status,
                "error": str(exc),
                "error_code": error_code,
            }
