from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.capture.connectors.base import ExternalListingRecord
from app.modules.capture.models import (
    CaptureJobModel,
    DemandExternalMatchModel,
    ExternalListingModel,
    SearchRunModel,
    SearchRunResultModel,
    SearchRunSourceModel,
)
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose
from app.modules.properties.application.matching import (
    MATCHING_VERSION,
    calculate_property_match,
    meets_required_constraints,
    normalize_search_text,
)
from app.modules.properties.domain.entities import Property, PropertyPurpose


@dataclass(frozen=True, slots=True)
class CaptureJobSnapshot:
    id: UUID
    tenant_id: UUID
    search_run_id: UUID
    demand_id: UUID
    source_id: str
    lease_token: UUID
    attempts: int
    max_attempts: int


class LostCaptureJobLease(RuntimeError):
    pass


SEARCH_CACHE_VERSION = "2026-08-13.1"


class FederatedSearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(
        self,
        tenant_id: UUID,
        demand: LeadDemand,
        source_ids: list[str],
        *,
        run_id: UUID | None = None,
        requested_by_user_id: UUID | None = None,
        catalog_version: str = SEARCH_CACHE_VERSION,
        cache_ttl_seconds: int = 86_400,
        force_refresh: bool = False,
        billing_reservation_key: str | None = None,
        max_attempts: int = 3,
    ) -> SearchRunModel:
        now = datetime.now(UTC)
        cache_key = build_search_cache_key(
            demand,
            source_ids,
            catalog_version=catalog_version,
            matching_version=MATCHING_VERSION,
        )
        cache_bucket = (
            int(now.timestamp() * 1_000_000)
            if force_refresh
            else int(now.timestamp()) // cache_ttl_seconds
        )
        run = SearchRunModel(
            id=run_id or uuid4(),
            tenant_id=tenant_id,
            demand_id=demand.id,
            requested_by_user_id=requested_by_user_id,
            status="queued",
            filters=_demand_filters(demand),
            source_count=len(source_ids),
            completed_source_count=0,
            result_count=0,
            cache_key=cache_key,
            cache_bucket=cache_bucket,
            cache_expires_at=now + timedelta(seconds=cache_ttl_seconds),
            catalog_version=catalog_version,
            matching_version=MATCHING_VERSION,
            force_refresh=force_refresh,
            billing_reservation_key=billing_reservation_key,
        )
        self.session.add(run)
        # The jobs and source rows reference the run through a composite tenant key.
        # Flush the parent explicitly so PostgreSQL always sees it before batched children.
        self.session.flush()
        for source_id in source_ids:
            self.session.add(
                SearchRunSourceModel(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    search_run_id=run.id,
                    source_id=source_id,
                    status="queued",
                )
            )
            self.session.add(
                CaptureJobModel(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    search_run_id=run.id,
                    demand_id=demand.id,
                    source_id=source_id,
                    status="queued",
                    attempts=0,
                    max_attempts=max_attempts,
                    available_at=now,
                )
            )
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_run(self, tenant_id: UUID, run_id: UUID) -> SearchRunModel | None:
        return self.session.scalar(
            select(SearchRunModel).where(
                SearchRunModel.tenant_id == tenant_id,
                SearchRunModel.id == run_id,
            )
        )

    def find_reusable_run(
        self,
        tenant_id: UUID,
        demand: LeadDemand,
        source_ids: list[str],
        *,
        catalog_version: str = SEARCH_CACHE_VERSION,
        include_expired_running: bool = True,
    ) -> SearchRunModel | None:
        """Return the newest run for the exact demand snapshot and source set.

        Running jobs are reused as well as terminal runs with at least one successful
        source. Fully failed runs remain retryable through a new execution.
        """
        now = datetime.now(UTC)
        cache_key = build_search_cache_key(
            demand,
            source_ids,
            catalog_version=catalog_version,
            matching_version=MATCHING_VERSION,
        )
        candidates = list(
            self.session.scalars(
                select(SearchRunModel)
                .where(
                    SearchRunModel.tenant_id == tenant_id,
                    SearchRunModel.demand_id == demand.id,
                    SearchRunModel.cache_key == cache_key,
                    SearchRunModel.status.in_(
                        ("queued", "running", "partial", "completed")
                    ),
                )
                .order_by(SearchRunModel.created_at.desc())
                .limit(5)
            ).all()
        )
        for run in candidates:
            running = run.status in {"queued", "running"}
            fresh = run.cache_expires_at is not None and run.cache_expires_at > now
            if (include_expired_running and running) or fresh:
                return run
        return None

    def list_run_sources(self, tenant_id: UUID, run_id: UUID) -> list[SearchRunSourceModel]:
        return list(
            self.session.scalars(
                select(SearchRunSourceModel)
                .where(
                    SearchRunSourceModel.tenant_id == tenant_id,
                    SearchRunSourceModel.search_run_id == run_id,
                )
                .order_by(SearchRunSourceModel.created_at, SearchRunSourceModel.source_id)
            ).all()
        )

    def latest_compatible_run(
        self,
        tenant_id: UUID,
        demand: LeadDemand,
        source_ids: list[str],
        *,
        catalog_version: str = SEARCH_CACHE_VERSION,
    ) -> SearchRunModel | None:
        if not source_ids:
            return None
        cache_key = build_search_cache_key(
            demand,
            source_ids,
            catalog_version=catalog_version,
            matching_version=MATCHING_VERSION,
        )
        compatible = self.session.scalar(
            select(SearchRunModel)
            .where(
                SearchRunModel.tenant_id == tenant_id,
                SearchRunModel.demand_id == demand.id,
                SearchRunModel.cache_key == cache_key,
            )
            .order_by(SearchRunModel.created_at.desc())
            .limit(1)
        )
        if compatible is not None:
            return compatible

        # Runs created before cache snapshots were introduced remain readable as
        # history, but only while their demand criteria still match. New runs never
        # use this compatibility path, so editing a demand cannot surface stale data.
        premium = source_ids == ["web_discovery"]
        legacy_runs = self.session.scalars(
            select(SearchRunModel)
            .where(
                SearchRunModel.tenant_id == tenant_id,
                SearchRunModel.demand_id == demand.id,
                SearchRunModel.cache_key.is_(None),
            )
            .order_by(SearchRunModel.created_at.desc())
            .limit(50)
        ).all()
        expected_filters = _demand_filters(demand)
        for run in legacy_runs:
            run_sources = {
                item.source_id for item in self.list_run_sources(tenant_id, run.id)
            }
            is_premium = run_sources == {"web_discovery"}
            if is_premium == premium and _legacy_filters_match(
                run.filters, expected_filters
            ):
                return run
        return None

    def list_results(
        self,
        tenant_id: UUID,
        run_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        fit_min: int | None = None,
        fit_max: int | None = None,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        run = self.get_run(tenant_id, run_id)
        if run is None:
            return []
        statement = (
            select(SearchRunResultModel, DemandExternalMatchModel.review_status)
            .outerjoin(
                DemandExternalMatchModel,
                (DemandExternalMatchModel.tenant_id == SearchRunResultModel.tenant_id)
                & (DemandExternalMatchModel.demand_id == run.demand_id)
                & (
                    DemandExternalMatchModel.external_listing_id
                    == SearchRunResultModel.external_listing_id
                ),
            )
            .where(
                SearchRunResultModel.tenant_id == tenant_id,
                SearchRunResultModel.search_run_id == run_id,
                or_(
                    DemandExternalMatchModel.review_status.is_(None),
                    DemandExternalMatchModel.review_status != "discarded",
                ),
            )
        )
        if fit_min is not None:
            statement = statement.where(SearchRunResultModel.fit_score >= fit_min)
        if fit_max is not None:
            statement = statement.where(SearchRunResultModel.fit_score <= fit_max)
        if source_id:
            statement = statement.where(SearchRunResultModel.source_id == source_id)
        rows = self.session.execute(
            statement.order_by(
                SearchRunResultModel.fit_score.desc(),
                SearchRunResultModel.confidence_score.desc(),
                SearchRunResultModel.created_at.desc(),
            )
        ).all()
        compatible_rows = [
            (result, review_status)
            for result, review_status in rows
            if _snapshot_meets_required_constraints(result.listing_snapshot, run.filters)
        ]
        return [
            _snapshot_result_payload(result, review_status or "new")
            for result, review_status in compatible_rows[offset : offset + limit]
        ]

    def get_result_for_capture(
        self,
        tenant_id: UUID,
        run_id: UUID,
        listing_id: UUID,
    ) -> tuple[UUID, dict[str, Any]] | None:
        row = self.session.execute(
            select(SearchRunModel, SearchRunResultModel, DemandExternalMatchModel)
            .join(
                SearchRunResultModel,
                (SearchRunResultModel.tenant_id == SearchRunModel.tenant_id)
                & (SearchRunResultModel.search_run_id == SearchRunModel.id),
            )
            .outerjoin(
                DemandExternalMatchModel,
                (DemandExternalMatchModel.tenant_id == SearchRunModel.tenant_id)
                & (DemandExternalMatchModel.demand_id == SearchRunModel.demand_id)
                & (
                    DemandExternalMatchModel.external_listing_id
                    == SearchRunResultModel.external_listing_id
                ),
            )
            .where(
                SearchRunModel.tenant_id == tenant_id,
                SearchRunModel.id == run_id,
                SearchRunResultModel.external_listing_id == listing_id,
                or_(
                    DemandExternalMatchModel.review_status.is_(None),
                    DemandExternalMatchModel.review_status != "discarded",
                ),
            )
        ).one_or_none()
        if row is None:
            return None
        run, result, _match = row
        listing = result.listing_snapshot
        if not _snapshot_meets_required_constraints(listing, run.filters):
            return None

        def decimal(value: Any) -> Decimal | None:
            return Decimal(str(value)) if value not in (None, "") else None

        purpose = str(run.filters.get("purpose") or "")
        price = (
            listing.get("rent_price")
            if purpose == "rent" and listing.get("rent_price") is not None
            else listing.get("sale_price")
            if purpose == "buy" and listing.get("sale_price") is not None
            else listing.get("price")
        )
        images = (
            [{"url": listing["primary_image_url"], "is_primary": True}]
            if listing.get("primary_image_url")
            else []
        )
        return run.demand_id, {
            "source": listing["source_id"],
            "source_url": listing["canonical_url"],
            "title": listing["title"],
            "city": listing["city"],
            "neighborhood": listing.get("neighborhood"),
            "price": decimal(price),
            "sale_price": decimal(listing.get("sale_price")),
            "rent_price": decimal(listing.get("rent_price")),
            "purpose": listing.get("purpose"),
            "property_type": listing.get("property_type"),
            "listing_code": f"{listing['source_id']}:{listing['source_listing_id']}",
            "description": listing.get("description"),
            "bedrooms": listing.get("bedrooms"),
            "suites": listing.get("suites"),
            "bathrooms": listing.get("bathrooms"),
            "parking_spaces": listing.get("parking_spaces"),
            "area": listing.get("area"),
            "land_area": listing.get("land_area"),
            "address": listing.get("address") or {},
            "details": {
                "external_listing_id": str(result.external_listing_id),
                "state": listing.get("state"),
                "fit_score": result.fit_score,
                "confidence_score": result.confidence_score,
                "condominium_fee": listing.get("condominium_fee"),
                "property_tax": listing.get("property_tax"),
                "primary_image_url": listing.get("primary_image_url"),
            },
            "images": images,
            "advertiser_name": listing.get("advertiser_name"),
            "advertiser_phone": listing.get("advertiser_phone"),
        }

    def mark_result_saved(
        self,
        tenant_id: UUID,
        run_id: UUID,
        listing_id: UUID,
        *,
        property_id: UUID | None = None,
        commit: bool = True,
    ) -> bool:
        run = self.get_run(tenant_id, run_id)
        if run is None:
            return False
        result = self.session.scalar(
            select(SearchRunResultModel).where(
                SearchRunResultModel.tenant_id == tenant_id,
                SearchRunResultModel.search_run_id == run_id,
                SearchRunResultModel.external_listing_id == listing_id,
            )
        )
        if result is None:
            return False
        match = self.session.scalar(
            select(DemandExternalMatchModel)
            .where(
                DemandExternalMatchModel.tenant_id == tenant_id,
                DemandExternalMatchModel.demand_id == run.demand_id,
                DemandExternalMatchModel.external_listing_id == listing_id,
            )
        )
        if match is None:
            return False
        match.review_status = "saved"
        match.saved_property_id = property_id
        match.updated_at = datetime.now(UTC)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return True

    def mark_result_unsaved(
        self,
        tenant_id: UUID,
        run_id: UUID,
        listing_id: UUID,
    ) -> tuple[UUID, UUID | None] | None:
        run = self.get_run(tenant_id, run_id)
        if run is None:
            return None
        match = self.session.scalar(
            select(DemandExternalMatchModel).where(
                DemandExternalMatchModel.tenant_id == tenant_id,
                DemandExternalMatchModel.demand_id == run.demand_id,
                DemandExternalMatchModel.external_listing_id == listing_id,
            )
        )
        if match is None:
            return None
        property_id = match.saved_property_id
        match.review_status = "new"
        match.saved_property_id = None
        match.updated_at = datetime.now(UTC)
        self.session.flush()
        return run.demand_id, property_id

    def claim_next(self, lease_seconds: int, worker_id: str) -> CaptureJobSnapshot | None:
        now = datetime.now(UTC)
        expired = list(
            self.session.scalars(
                select(CaptureJobModel)
                .where(
                    CaptureJobModel.status == "processing",
                    CaptureJobModel.lease_expires_at < now,
                )
                .with_for_update(skip_locked=True)
            ).all()
        )
        for job in expired:
            exhausted = job.attempts >= job.max_attempts
            job.status = "failed" if exhausted else "retrying"
            job.available_at = now
            job.last_error = "Worker perdeu o lease durante a captura"
            self._release(job, now)
            source = self._source(job.tenant_id, job.search_run_id, job.source_id)
            if source is not None:
                source.status = "failed" if exhausted else "queued"
                source.error_code = "lease_expired"
                source.error = job.last_error

        job = self.session.scalar(
            select(CaptureJobModel)
            .where(
                CaptureJobModel.status.in_(("queued", "retrying")),
                CaptureJobModel.available_at <= now,
            )
            .order_by(CaptureJobModel.available_at, CaptureJobModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            self.session.commit()
            return None
        token = uuid4()
        job.status = "processing"
        job.attempts += 1
        job.locked_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.lease_owner = worker_id
        job.lease_token = token
        job.updated_at = now
        source = self._source(job.tenant_id, job.search_run_id, job.source_id)
        if source is not None:
            source.status = "running"
            source.started_at = source.started_at or now
            source.error_code = None
            source.error = None
        run = self.session.get(SearchRunModel, job.search_run_id)
        if run is not None:
            run.status = "running"
            run.started_at = run.started_at or now
            run.updated_at = now
        snapshot = CaptureJobSnapshot(
            id=job.id,
            tenant_id=job.tenant_id,
            search_run_id=job.search_run_id,
            demand_id=job.demand_id,
            source_id=job.source_id,
            lease_token=token,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
        )
        self.session.commit()
        return snapshot

    def upsert_and_match(
        self,
        job: CaptureJobSnapshot,
        demand: LeadDemand,
        record: ExternalListingRecord,
    ) -> tuple[ExternalListingModel, bool]:
        now = datetime.now(UTC)
        # Abort before persisting results when the run was cancelled or its lease was lost.
        self._leased(job)
        listing = self.session.scalar(
            select(ExternalListingModel).where(
                ExternalListingModel.source_id == record.source_id,
                ExternalListingModel.source_listing_id == record.source_listing_id,
            )
        )
        if listing is None:
            listing_id = self.session.scalar(
                insert(ExternalListingModel)
                .values(
                    id=uuid4(),
                    source_id=record.source_id,
                    source_listing_id=record.source_listing_id,
                    canonical_url=record.canonical_url,
                    title=record.title,
                    city=record.city,
                    content_hash=record.content_hash(),
                    first_seen_at=now,
                    last_seen_at=now,
                    last_checked_at=now,
                )
                .on_conflict_do_nothing()
                .returning(ExternalListingModel.id)
            )
            if listing_id is not None:
                listing = self.session.get(ExternalListingModel, listing_id)
            else:
                listing = self.session.scalar(
                    select(ExternalListingModel).where(
                        ExternalListingModel.source_id == record.source_id,
                        or_(
                            ExternalListingModel.source_listing_id
                            == record.source_listing_id,
                            ExternalListingModel.canonical_url == record.canonical_url,
                        ),
                    )
                )
            if listing is None:
                raise RuntimeError("External listing upsert did not return a record")
        self._apply_record(listing, record, now)
        self.session.flush()

        property_for_match = _property_for_match(record, demand.tenant_id)
        if not meets_required_constraints(property_for_match, demand):
            return listing, False
        match = calculate_property_match(property_for_match, demand)
        if match.score < 40:
            return listing, False
        confidence = min(record.extraction_confidence, record.completeness_score())
        persisted_match = self.session.scalar(
            select(DemandExternalMatchModel).where(
                DemandExternalMatchModel.tenant_id == job.tenant_id,
                DemandExternalMatchModel.demand_id == job.demand_id,
                DemandExternalMatchModel.external_listing_id == listing.id,
            )
        )
        if persisted_match is None:
            persisted_match = DemandExternalMatchModel(
                id=uuid4(),
                tenant_id=job.tenant_id,
                demand_id=job.demand_id,
                external_listing_id=listing.id,
                last_search_run_id=job.search_run_id,
                fit_score=match.score,
                confidence_score=confidence,
                matched=match.matched,
                tradeoffs=match.tradeoffs,
                review_status="new",
            )
            self.session.add(persisted_match)
        else:
            persisted_match.last_search_run_id = job.search_run_id
            persisted_match.fit_score = match.score
            persisted_match.confidence_score = confidence
            persisted_match.matched = match.matched
            persisted_match.tradeoffs = match.tradeoffs
            persisted_match.updated_at = now
        self.session.execute(
            insert(SearchRunResultModel)
            .values(
                id=uuid4(),
                tenant_id=job.tenant_id,
                search_run_id=job.search_run_id,
                external_listing_id=listing.id,
                source_id=record.source_id,
                fit_score=match.score,
                confidence_score=confidence,
                matched=match.matched,
                tradeoffs=match.tradeoffs,
                listing_snapshot=_listing_snapshot(listing),
                created_at=now,
            )
            .on_conflict_do_nothing(
                constraint="uq_capture_search_run_result"
            )
        )
        # Sessions intentionally disable autoflush; persist the match before the run
        # aggregates its result count or another duplicate record is evaluated.
        self.session.flush()
        return listing, True

    def complete(
        self,
        job: CaptureJobSnapshot,
        *,
        discovered_count: int,
        imported_count: int,
        parser_version: str,
    ) -> None:
        now = datetime.now(UTC)
        persisted = self._leased(job)
        persisted.status = "completed"
        persisted.last_error = None
        self._release(persisted, now)
        source = self._source(job.tenant_id, job.search_run_id, job.source_id)
        if source is not None:
            source.status = "completed"
            source.discovered_count = discovered_count
            source.imported_count = imported_count
            source.parser_version = parser_version
            source.error_code = None
            source.error = None
            source.completed_at = now
            source.updated_at = now
        self._refresh_run(job.tenant_id, job.search_run_id, now)
        self.session.commit()

    def fail(
        self,
        job: CaptureJobSnapshot,
        error: str,
        *,
        error_code: str,
        retryable: bool,
        backoff_seconds: int,
    ) -> str:
        now = datetime.now(UTC)
        try:
            persisted = self._leased(job)
        except LostCaptureJobLease:
            self.session.rollback()
            return "cancelled"
        exhausted = not retryable or persisted.attempts >= persisted.max_attempts
        persisted.status = "failed" if exhausted else "retrying"
        persisted.last_error = error[:4000]
        persisted.available_at = now + timedelta(
            seconds=backoff_seconds * (2 ** max(persisted.attempts - 1, 0))
        )
        self._release(persisted, now)
        source = self._source(job.tenant_id, job.search_run_id, job.source_id)
        if source is not None:
            source.status = (
                "blocked"
                if exhausted and error_code == "source_blocked"
                else "failed"
                if exhausted
                else "queued"
            )
            source.error_code = error_code
            source.error = error[:4000]
            source.completed_at = now if exhausted else None
            source.updated_at = now
        self._refresh_run(job.tenant_id, job.search_run_id, now)
        self.session.commit()
        return persisted.status

    def cancel_run(self, tenant_id: UUID, run_id: UUID) -> SearchRunModel | None:
        run = self.get_run(tenant_id, run_id)
        if run is None:
            return None
        if run.status in {"completed", "partial", "failed", "cancelled"}:
            return run
        now = datetime.now(UTC)
        run.status = "cancelled"
        run.cancel_requested_at = now
        run.completed_at = now
        run.updated_at = now
        jobs = self.session.scalars(
            select(CaptureJobModel).where(
                CaptureJobModel.tenant_id == tenant_id,
                CaptureJobModel.search_run_id == run_id,
                CaptureJobModel.status.in_(("queued", "retrying", "processing")),
            )
        ).all()
        for job in jobs:
            job.status = "cancelled"
            job.last_error = "Busca cancelada pelo usuário"
            self._release(job, now)
        sources = self.list_run_sources(tenant_id, run_id)
        for source in sources:
            if source.status in {"queued", "running"}:
                source.status = "cancelled"
                source.error_code = "cancelled"
                source.error = "Busca cancelada pelo usuário"
                source.completed_at = now
                source.updated_at = now
        run.completed_source_count = len(
            [source for source in sources if source.status != "queued"]
        )
        self.session.commit()
        self.session.refresh(run)
        return run

    def retry_source(
        self,
        tenant_id: UUID,
        run_id: UUID,
        source_id: str,
    ) -> SearchRunModel | None:
        run = self.get_run(tenant_id, run_id)
        source = self._source(tenant_id, run_id, source_id) if run else None
        if run is None or source is None:
            return None
        if source.status not in {"failed", "blocked"}:
            raise ValueError("Somente fontes com falha podem ser executadas novamente")
        now = datetime.now(UTC)
        job = self.session.scalar(
            select(CaptureJobModel).where(
                CaptureJobModel.tenant_id == tenant_id,
                CaptureJobModel.search_run_id == run_id,
                CaptureJobModel.source_id == source_id,
            )
        )
        if job is None:
            return None
        self.session.execute(
            delete(SearchRunResultModel).where(
                SearchRunResultModel.tenant_id == tenant_id,
                SearchRunResultModel.search_run_id == run_id,
                SearchRunResultModel.source_id == source_id,
            )
        )
        job.status = "queued"
        job.attempts = 0
        job.available_at = now
        job.last_error = None
        self._release(job, now)
        source.status = "queued"
        source.discovered_count = 0
        source.imported_count = 0
        source.error_code = None
        source.error = None
        source.completed_at = None
        source.updated_at = now
        run.status = "queued"
        run.completed_at = None
        run.error = None
        run.updated_at = now
        self._refresh_run(tenant_id, run_id, now)
        self.session.commit()
        self.session.refresh(run)
        return run

    def _refresh_run(self, tenant_id: UUID, run_id: UUID, now: datetime) -> None:
        run = self.session.scalar(
            select(SearchRunModel).where(
                SearchRunModel.tenant_id == tenant_id,
                SearchRunModel.id == run_id,
            )
        )
        if run is None:
            return
        sources = self.list_run_sources(tenant_id, run_id)
        terminal = [
            source for source in sources if source.status in {"completed", "failed", "blocked"}
        ]
        successes = [source for source in sources if source.status == "completed"]
        failures = [source for source in sources if source.status in {"failed", "blocked"}]
        run.completed_source_count = len(terminal)
        run.result_count = int(
            self.session.scalar(
                select(func.count(SearchRunResultModel.id)).where(
                    SearchRunResultModel.tenant_id == tenant_id,
                    SearchRunResultModel.search_run_id == run_id,
                )
            )
            or 0
        )
        if run.status == "cancelled":
            return
        if len(terminal) == len(sources):
            if successes and failures:
                run.status = "partial"
            elif successes:
                run.status = "completed"
            else:
                run.status = "failed"
            run.completed_at = now
        else:
            run.status = "running"
        run.updated_at = now

    def _source(self, tenant_id: UUID, run_id: UUID, source_id: str) -> SearchRunSourceModel | None:
        return self.session.scalar(
            select(SearchRunSourceModel).where(
                SearchRunSourceModel.tenant_id == tenant_id,
                SearchRunSourceModel.search_run_id == run_id,
                SearchRunSourceModel.source_id == source_id,
            )
        )

    def _leased(self, job: CaptureJobSnapshot) -> CaptureJobModel:
        persisted = self.session.scalar(
            select(CaptureJobModel).where(
                CaptureJobModel.id == job.id,
                CaptureJobModel.status == "processing",
                CaptureJobModel.lease_token == job.lease_token,
            )
        )
        if persisted is None:
            raise LostCaptureJobLease(str(job.id))
        return persisted

    @staticmethod
    def _release(job: CaptureJobModel, now: datetime) -> None:
        job.locked_at = None
        job.lease_expires_at = None
        job.lease_owner = None
        job.lease_token = None
        job.updated_at = now

    @staticmethod
    def _apply_record(
        listing: ExternalListingModel, record: ExternalListingRecord, now: datetime
    ) -> None:
        listing.canonical_url = record.canonical_url
        listing.title = record.title
        listing.description = record.description
        listing.property_type = record.property_type
        listing.status = "active"
        listing.state = record.state
        listing.city = record.city
        listing.neighborhood = record.neighborhood
        listing.address = record.address
        listing.latitude = record.latitude
        listing.longitude = record.longitude
        listing.price = record.price
        # A response is a current offer snapshot. Clear an alternative price when the
        # source no longer advertises it instead of retaining stale cross-run data.
        listing.sale_price = record.sale_price
        listing.rent_price = record.rent_price
        if listing.sale_price is not None and listing.rent_price is not None:
            listing.purpose = "both"
        elif listing.rent_price is not None:
            listing.purpose = "rent"
        elif listing.sale_price is not None:
            listing.purpose = "buy"
        else:
            listing.purpose = record.purpose
        listing.condominium_fee = record.condominium_fee
        listing.property_tax = record.property_tax
        listing.bedrooms = record.bedrooms
        listing.suites = record.suites
        listing.bathrooms = record.bathrooms
        listing.parking_spaces = record.parking_spaces
        listing.area = record.area
        listing.land_area = record.land_area
        listing.primary_image_url = record.primary_image_url
        listing.advertiser_name = record.advertiser_name
        listing.advertiser_phone = record.advertiser_phone
        listing.raw_data = record.raw_data
        listing.content_hash = record.content_hash()
        listing.extraction_confidence = record.extraction_confidence
        listing.completeness_score = record.completeness_score()
        listing.last_seen_at = now
        listing.last_checked_at = now
        listing.suspected_inactive_at = None
        listing.inactive_at = None
        listing.updated_at = now


def _demand_filters(demand: LeadDemand) -> dict[str, Any]:
    return {
        "purpose": demand.purpose.value if demand.purpose else None,
        "property_type": demand.property_type,
        "city": demand.city,
        "state": demand.state,
        "neighborhoods": demand.neighborhoods,
        "price_min": str(demand.price_min) if demand.price_min is not None else None,
        "price_max": str(demand.price_max) if demand.price_max is not None else None,
        "bedrooms": demand.bedrooms,
        "parking_spaces": demand.parking_spaces,
        "min_area": demand.min_area,
    }


def _legacy_filters_match(
    persisted: dict[str, Any], expected: dict[str, Any]
) -> bool:
    for field, expected_value in expected.items():
        persisted_value = persisted.get(field)
        if field == "neighborhoods":
            if sorted(persisted_value or []) != sorted(expected_value or []):
                return False
        elif field in {"price_min", "price_max"}:
            normalized_persisted = (
                str(persisted_value) if persisted_value is not None else None
            )
            if normalized_persisted != expected_value:
                return False
        elif persisted_value != expected_value:
            return False
    return True


def _snapshot_meets_required_constraints(
    listing: dict[str, Any], filters: dict[str, Any]
) -> bool:
    purpose = str(filters.get("purpose") or "")
    listing_purpose = str(listing.get("purpose") or "")
    if purpose and listing_purpose not in {purpose, "both"}:
        return False
    city = str(filters.get("city") or "")
    if city and normalize_search_text(
        str(listing.get("city") or "")
    ) != normalize_search_text(city):
        return False
    state = normalize_search_text(str(filters.get("state") or ""))
    listing_state = normalize_search_text(str(listing.get("state") or ""))
    if state and listing_state and state != listing_state:
        return False

    minimum = _decimal_snapshot_value(filters.get("price_min"))
    maximum = _decimal_snapshot_value(filters.get("price_max"))
    if minimum is None and maximum is None:
        return True
    preferred_key = "rent_price" if purpose == "rent" else "sale_price"
    price = _decimal_snapshot_value(listing.get(preferred_key))
    if price is None and listing_purpose == purpose:
        price = _decimal_snapshot_value(listing.get("price"))
    if price is None:
        return False
    return (minimum is None or price >= minimum) and (
        maximum is None or price <= maximum
    )


def _decimal_snapshot_value(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (ArithmeticError, ValueError):
        return None


def _property_for_match(record: ExternalListingRecord, tenant_id: UUID) -> Property:
    purpose = PropertyPurpose(record.purpose) if record.purpose in {"buy", "rent", "both"} else None
    return Property(
        tenant_id=tenant_id,
        source=record.source_id,
        source_url=record.canonical_url,
        title=record.title,
        city=record.city,
        neighborhood=record.neighborhood,
        price=record.price,
        sale_price=record.sale_price,
        rent_price=record.rent_price,
        purpose=purpose,
        property_type=record.property_type,
        description=record.description,
        bedrooms=record.bedrooms,
        suites=record.suites,
        bathrooms=record.bathrooms,
        parking_spaces=record.parking_spaces,
        area=record.area,
        land_area=record.land_area,
        address={**record.address, "state": record.state or record.address.get("state")},
        advertiser_name=record.advertiser_name,
        advertiser_phone=record.advertiser_phone,
    )


def build_search_cache_key(
    demand: LeadDemand,
    source_ids: list[str],
    *,
    catalog_version: str,
    matching_version: str,
) -> str:
    material = {
        "cache_version": SEARCH_CACHE_VERSION,
        "catalog_version": catalog_version,
        "matching_version": matching_version,
        "filters": _demand_filters(demand),
        "sources": sorted(source_ids),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def demand_from_search_snapshot(current: LeadDemand, filters: dict[str, Any]) -> LeadDemand:
    def decimal(value: Any) -> Decimal | None:
        return Decimal(str(value)) if value not in (None, "") else None

    return LeadDemand(
        id=current.id,
        tenant_id=current.tenant_id,
        contact_id=current.contact_id,
        conversation_id=current.conversation_id,
        lead_name=current.lead_name,
        phone=current.phone,
        purpose=LeadPurpose(filters["purpose"]) if filters.get("purpose") else None,
        property_type=filters.get("property_type"),
        city=filters.get("city"),
        state=filters.get("state"),
        neighborhoods=list(filters.get("neighborhoods") or []),
        price_min=decimal(filters.get("price_min")),
        price_max=decimal(filters.get("price_max")),
        bedrooms=filters.get("bedrooms"),
        parking_spaces=filters.get("parking_spaces"),
        min_area=filters.get("min_area"),
        notes=current.notes,
        status=current.status,
        responsible_user_id=current.responsible_user_id,
        crm_contact_id=current.crm_contact_id,
        crm_deal_id=current.crm_deal_id,
        created_at=current.created_at,
        updated_at=current.updated_at,
    )


def _listing_snapshot(listing: ExternalListingModel) -> dict[str, Any]:
    def decimal(value: Any) -> str | None:
        return str(value) if value is not None else None

    return {
        "id": str(listing.id),
        "source_id": listing.source_id,
        "source_domain": (
            urlsplit(listing.canonical_url).hostname or ""
        ).removeprefix("www."),
        "source_listing_id": listing.source_listing_id,
        "canonical_url": listing.canonical_url,
        "title": listing.title,
        "description": listing.description,
        "purpose": listing.purpose,
        "property_type": listing.property_type,
        "state": listing.state,
        "city": listing.city,
        "neighborhood": listing.neighborhood,
        "address": listing.address,
        "price": decimal(listing.price),
        "sale_price": decimal(listing.sale_price),
        "rent_price": decimal(listing.rent_price),
        "condominium_fee": decimal(listing.condominium_fee),
        "property_tax": decimal(listing.property_tax),
        "bedrooms": listing.bedrooms,
        "suites": listing.suites,
        "bathrooms": listing.bathrooms,
        "parking_spaces": listing.parking_spaces,
        "area": listing.area,
        "land_area": listing.land_area,
        "primary_image_url": listing.primary_image_url,
        "advertiser_name": listing.advertiser_name,
        "advertiser_phone": listing.advertiser_phone,
        "last_seen_at": listing.last_seen_at.isoformat(),
    }


def _snapshot_result_payload(
    result: SearchRunResultModel,
    review_status: str,
) -> dict[str, Any]:
    payload = dict(result.listing_snapshot)
    payload.update(
        {
            "fit_score": result.fit_score,
            "confidence_score": result.confidence_score,
            "matched": result.matched,
            "tradeoffs": result.tradeoffs,
            "review_status": review_status,
        }
    )
    return payload
