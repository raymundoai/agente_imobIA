from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.capture.connectors.base import ExternalListingRecord
from app.modules.capture.models import (
    CaptureJobModel,
    DemandExternalMatchModel,
    ExternalListingModel,
    SearchRunModel,
    SearchRunSourceModel,
)
from app.modules.leads.domain.entities import LeadDemand
from app.modules.properties.application.matching import calculate_property_match
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


class FederatedSearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(
        self,
        tenant_id: UUID,
        demand: LeadDemand,
        source_ids: list[str],
        *,
        max_attempts: int = 3,
    ) -> SearchRunModel:
        now = datetime.now(UTC)
        run = SearchRunModel(
            id=uuid4(),
            tenant_id=tenant_id,
            demand_id=demand.id,
            status="queued",
            filters=_demand_filters(demand),
            source_count=len(source_ids),
            completed_source_count=0,
            result_count=0,
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

    def list_results(self, tenant_id: UUID, run_id: UUID) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(DemandExternalMatchModel, ExternalListingModel)
            .join(
                ExternalListingModel,
                ExternalListingModel.id == DemandExternalMatchModel.external_listing_id,
            )
            .where(
                DemandExternalMatchModel.tenant_id == tenant_id,
                DemandExternalMatchModel.last_search_run_id == run_id,
                DemandExternalMatchModel.review_status != "discarded",
            )
            .order_by(
                DemandExternalMatchModel.fit_score.desc(),
                DemandExternalMatchModel.confidence_score.desc(),
                ExternalListingModel.last_seen_at.desc(),
            )
        ).all()
        return [_result_payload(match, listing) for match, listing in rows]

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
        listing = self.session.scalar(
            select(ExternalListingModel).where(
                ExternalListingModel.source_id == record.source_id,
                ExternalListingModel.source_listing_id == record.source_listing_id,
            )
        )
        if listing is None:
            listing = ExternalListingModel(
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
            self.session.add(listing)
        self._apply_record(listing, record, now)
        self.session.flush()

        match = calculate_property_match(_property_for_match(record, demand.tenant_id), demand)
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
        persisted = self._leased(job)
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
                select(func.count(DemandExternalMatchModel.id)).where(
                    DemandExternalMatchModel.tenant_id == tenant_id,
                    DemandExternalMatchModel.last_search_run_id == run_id,
                )
            )
            or 0
        )
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
        if record.sale_price is not None:
            listing.sale_price = record.sale_price
        if record.rent_price is not None:
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
        "neighborhoods": demand.neighborhoods,
        "price_min": str(demand.price_min) if demand.price_min is not None else None,
        "price_max": str(demand.price_max) if demand.price_max is not None else None,
        "bedrooms": demand.bedrooms,
        "parking_spaces": demand.parking_spaces,
        "min_area": demand.min_area,
    }


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
        address=record.address,
        advertiser_name=record.advertiser_name,
        advertiser_phone=record.advertiser_phone,
    )


def _result_payload(
    match: DemandExternalMatchModel, listing: ExternalListingModel
) -> dict[str, Any]:
    return {
        "id": str(listing.id),
        "source_id": listing.source_id,
        "source_listing_id": listing.source_listing_id,
        "canonical_url": listing.canonical_url,
        "title": listing.title,
        "description": listing.description,
        "purpose": listing.purpose,
        "property_type": listing.property_type,
        "state": listing.state,
        "city": listing.city,
        "neighborhood": listing.neighborhood,
        "price": str(listing.price) if listing.price is not None else None,
        "sale_price": str(listing.sale_price) if listing.sale_price is not None else None,
        "rent_price": str(listing.rent_price) if listing.rent_price is not None else None,
        "bedrooms": listing.bedrooms,
        "bathrooms": listing.bathrooms,
        "parking_spaces": listing.parking_spaces,
        "area": listing.area,
        "primary_image_url": listing.primary_image_url,
        "advertiser_name": listing.advertiser_name,
        "fit_score": match.fit_score,
        "confidence_score": match.confidence_score,
        "matched": match.matched,
        "tradeoffs": match.tradeoffs,
        "review_status": match.review_status,
        "last_seen_at": listing.last_seen_at,
    }
