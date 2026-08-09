"""Add the federated external listing index and durable search jobs.

Revision ID: 20260808_0021
Revises: 20260806_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260808_0021"
down_revision = "20260806_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "external_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_listing_id", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("purpose", sa.Text()),
        sa.Column("property_type", sa.Text()),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("state", sa.Text()),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("neighborhood", sa.Text()),
        sa.Column("address", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7)),
        sa.Column("longitude", sa.Numeric(10, 7)),
        sa.Column("price", sa.Numeric(14, 2)),
        sa.Column("sale_price", sa.Numeric(14, 2)),
        sa.Column("rent_price", sa.Numeric(14, 2)),
        sa.Column("condominium_fee", sa.Numeric(14, 2)),
        sa.Column("property_tax", sa.Numeric(14, 2)),
        sa.Column("bedrooms", sa.Integer()),
        sa.Column("suites", sa.Integer()),
        sa.Column("bathrooms", sa.Integer()),
        sa.Column("parking_spaces", sa.Integer()),
        sa.Column("area", sa.Integer()),
        sa.Column("land_area", sa.Integer()),
        sa.Column("primary_image_url", sa.Text()),
        sa.Column("advertiser_name", sa.Text()),
        sa.Column("advertiser_phone", sa.Text()),
        sa.Column("raw_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("extraction_confidence", sa.Integer(), server_default="70", nullable=False),
        sa.Column("completeness_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("suspected_inactive_at", sa.DateTime(timezone=True)),
        sa.Column("inactive_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(
            "purpose IN ('buy', 'rent', 'both') OR purpose IS NULL",
            name="ck_external_listings_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspected_inactive', 'inactive')",
            name="ck_external_listings_status",
        ),
        sa.CheckConstraint(
            "extraction_confidence BETWEEN 0 AND 100",
            name="ck_external_listings_extraction_confidence",
        ),
        sa.CheckConstraint(
            "completeness_score BETWEEN 0 AND 100",
            name="ck_external_listings_completeness_score",
        ),
        sa.UniqueConstraint(
            "source_id",
            "source_listing_id",
            name="uq_external_listings_source_listing_id",
        ),
        sa.UniqueConstraint("source_id", "canonical_url", name="uq_external_listings_source_url"),
    )
    op.create_index(
        "ix_external_listings_location",
        "external_listings",
        ["state", "city", "neighborhood"],
    )
    op.create_index(
        "ix_external_listings_filters",
        "external_listings",
        ["purpose", "property_type", "price"],
    )
    op.create_index(
        "ix_external_listings_freshness", "external_listings", ["status", "last_seen_at"]
    )

    op.create_table(
        "capture_search_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("filters", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("source_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_source_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("result_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'partial', 'completed', 'failed', 'cancelled')",
            name="ck_capture_search_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "demand_id"],
            ["lead_demands.tenant_id", "lead_demands.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_capture_search_runs_tenant_id_id"),
    )
    op.create_index(
        "ix_capture_search_runs_tenant_created",
        "capture_search_runs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_capture_search_runs_tenant_demand",
        "capture_search_runs",
        ["tenant_id", "demand_id"],
    )

    op.create_table(
        "capture_search_run_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("search_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("discovered_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("parser_version", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'blocked')",
            name="ck_capture_search_run_sources_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "search_run_id"],
            ["capture_search_runs.tenant_id", "capture_search_runs.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("search_run_id", "source_id", name="uq_search_run_source"),
    )
    op.create_index(
        "ix_capture_search_run_sources_run",
        "capture_search_run_sources",
        ["tenant_id", "search_run_id"],
    )

    op.create_table(
        "demand_external_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "external_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("external_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last_search_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("matched", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("tradeoffs", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("review_status", sa.Text(), server_default="new", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "fit_score BETWEEN 0 AND 100", name="ck_demand_external_matches_fit_score"
        ),
        sa.CheckConstraint(
            "confidence_score BETWEEN 0 AND 100",
            name="ck_demand_external_matches_confidence_score",
        ),
        sa.CheckConstraint(
            "review_status IN ('new', 'reviewed', 'saved', 'contacted', 'discarded')",
            name="ck_demand_external_matches_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "demand_id"],
            ["lead_demands.tenant_id", "lead_demands.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "last_search_run_id"],
            ["capture_search_runs.tenant_id", "capture_search_runs.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "demand_id", "external_listing_id", name="uq_demand_external_match"
        ),
    )
    op.create_index(
        "ix_demand_external_matches_demand",
        "demand_external_matches",
        ["tenant_id", "demand_id", "fit_score"],
    )
    op.create_index(
        "ix_demand_external_matches_run",
        "demand_external_matches",
        ["tenant_id", "last_search_run_id"],
    )

    op.create_table(
        "capture_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("search_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("last_error", sa.Text()),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'retrying', 'completed', 'failed')",
            name="ck_capture_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "search_run_id"],
            ["capture_search_runs.tenant_id", "capture_search_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "demand_id"],
            ["lead_demands.tenant_id", "lead_demands.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("search_run_id", "source_id", name="uq_capture_job_run_source"),
    )
    op.create_index(
        "ix_capture_jobs_claim",
        "capture_jobs",
        ["status", "available_at", "created_at"],
    )
    op.create_index("ix_capture_jobs_tenant_run", "capture_jobs", ["tenant_id", "search_run_id"])


def downgrade() -> None:
    op.drop_table("capture_jobs")
    op.drop_table("demand_external_matches")
    op.drop_table("capture_search_run_sources")
    op.drop_table("capture_search_runs")
    op.drop_table("external_listings")
