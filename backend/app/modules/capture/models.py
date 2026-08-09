from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class ExternalListingModel(Base):
    """A source listing shared by every tenant using the federated index."""

    __tablename__ = "external_listings"
    __table_args__ = (
        CheckConstraint("purpose IN ('buy', 'rent', 'both') OR purpose IS NULL", name="purpose"),
        CheckConstraint("status IN ('active', 'suspected_inactive', 'inactive')", name="status"),
        CheckConstraint("extraction_confidence BETWEEN 0 AND 100", name="extraction_confidence"),
        CheckConstraint("completeness_score BETWEEN 0 AND 100", name="completeness_score"),
        UniqueConstraint(
            "source_id",
            "source_listing_id",
            name="uq_external_listings_source_listing_id",
        ),
        UniqueConstraint("source_id", "canonical_url", name="uq_external_listings_source_url"),
        Index("ix_external_listings_location", "state", "city", "neighborhood"),
        Index("ix_external_listings_filters", "purpose", "property_type", "price"),
        Index("ix_external_listings_freshness", "status", "last_seen_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_listing_id: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    property_type: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default="active"
    )
    state: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text, nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(Text)
    address: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    condominium_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    property_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    suites: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    parking_spaces: Mapped[int | None] = mapped_column(Integer)
    area: Mapped[int | None] = mapped_column(Integer)
    land_area: Mapped[int | None] = mapped_column(Integer)
    primary_image_url: Mapped[str | None] = mapped_column(Text)
    advertiser_name: Mapped[str | None] = mapped_column(Text)
    advertiser_phone: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=70, server_default="70"
    )
    completeness_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    suspected_inactive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inactive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SearchRunModel(Base):
    __tablename__ = "capture_search_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'partial', 'completed', 'failed', 'cancelled')",
            name="status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "demand_id"],
            ["lead_demands.tenant_id", "lead_demands.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_capture_search_runs_tenant_id_id"),
        Index("ix_capture_search_runs_tenant_created", "tenant_id", "created_at"),
        Index("ix_capture_search_runs_tenant_demand", "tenant_id", "demand_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    demand_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="queued", server_default="queued"
    )
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SearchRunSourceModel(Base):
    __tablename__ = "capture_search_run_sources"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'blocked')",
            name="status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "search_run_id"],
            ["capture_search_runs.tenant_id", "capture_search_runs.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("search_run_id", "source_id", name="uq_search_run_source"),
        Index("ix_capture_search_run_sources_run", "tenant_id", "search_run_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    search_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="queued", server_default="queued"
    )
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DemandExternalMatchModel(Base):
    __tablename__ = "demand_external_matches"
    __table_args__ = (
        CheckConstraint("fit_score BETWEEN 0 AND 100", name="fit_score"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="confidence_score"),
        CheckConstraint(
            "review_status IN ('new', 'reviewed', 'saved', 'contacted', 'discarded')",
            name="review_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "demand_id"],
            ["lead_demands.tenant_id", "lead_demands.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "last_search_run_id"],
            ["capture_search_runs.tenant_id", "capture_search_runs.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id", "demand_id", "external_listing_id", name="uq_demand_external_match"
        ),
        Index("ix_demand_external_matches_demand", "tenant_id", "demand_id", "fit_score"),
        Index("ix_demand_external_matches_run", "tenant_id", "last_search_run_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    demand_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    external_listing_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("external_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    last_search_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    matched: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    tradeoffs: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="new", server_default="new"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaptureJobModel(Base):
    __tablename__ = "capture_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'retrying', 'completed', 'failed')",
            name="status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "search_run_id"],
            ["capture_search_runs.tenant_id", "capture_search_runs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "demand_id"],
            ["lead_demands.tenant_id", "lead_demands.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("search_run_id", "source_id", name="uq_capture_job_run_source"),
        Index("ix_capture_jobs_claim", "status", "available_at", "created_at"),
        Index("ix_capture_jobs_tenant_run", "tenant_id", "search_run_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    search_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    demand_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="queued", server_default="queued"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_token: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
