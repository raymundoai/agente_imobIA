"""Make federated search history immutable, cacheable and auditable.

Revision ID: 20260813_0022
Revises: 20260808_0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260813_0022"
down_revision = "20260808_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead_demands", sa.Column("state", sa.Text()))
    op.create_check_constraint(
        "ck_lead_demands_price_range",
        "lead_demands",
        "price_min IS NULL OR price_max IS NULL OR price_min <= price_max",
    )

    op.add_column(
        "capture_search_runs",
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("capture_search_runs", sa.Column("cache_key", sa.Text()))
    op.add_column("capture_search_runs", sa.Column("cache_bucket", sa.BigInteger()))
    op.add_column(
        "capture_search_runs", sa.Column("cache_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column("capture_search_runs", sa.Column("catalog_version", sa.Text()))
    op.add_column("capture_search_runs", sa.Column("matching_version", sa.Text()))
    op.add_column(
        "capture_search_runs",
        sa.Column("force_refresh", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "capture_search_runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True))
    )
    op.add_column("capture_search_runs", sa.Column("billing_reservation_key", sa.Text()))
    op.create_index(
        "uq_capture_search_runs_cache_bucket",
        "capture_search_runs",
        ["tenant_id", "demand_id", "cache_key", "cache_bucket"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'partial', 'completed') AND NOT force_refresh"
        ),
    )

    op.add_column(
        "demand_external_matches",
        sa.Column(
            "saved_property_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("properties.id", ondelete="SET NULL"),
        ),
    )
    op.execute(
        """
        UPDATE demand_external_matches m
        SET saved_property_id = p.id
        FROM external_listings l, properties p, property_demand_matches pm
        WHERE m.external_listing_id = l.id
          AND p.tenant_id = m.tenant_id
          AND p.listing_code = l.source_id || ':' || l.source_listing_id
          AND pm.tenant_id = m.tenant_id
          AND pm.demand_id = m.demand_id
          AND pm.property_id = p.id
          AND m.review_status = 'saved'
        """
    )

    op.drop_constraint("ck_capture_jobs_status", "capture_jobs", type_="check")
    op.create_check_constraint(
        "ck_capture_jobs_status",
        "capture_jobs",
        "status IN ('queued', 'processing', 'retrying', 'completed', 'failed', 'cancelled')",
    )
    op.drop_constraint(
        "ck_capture_search_run_sources_status",
        "capture_search_run_sources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_capture_search_run_sources_status",
        "capture_search_run_sources",
        "status IN ('queued', 'running', 'completed', 'failed', 'blocked', 'cancelled')",
    )

    op.create_table(
        "capture_search_run_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("search_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "external_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("external_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("matched", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("tradeoffs", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("listing_snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fit_score BETWEEN 0 AND 100",
            name="ck_capture_search_run_results_fit_score",
        ),
        sa.CheckConstraint(
            "confidence_score BETWEEN 0 AND 100",
            name="ck_capture_search_run_results_confidence_score",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "search_run_id"],
            ["capture_search_runs.tenant_id", "capture_search_runs.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "search_run_id",
            "external_listing_id",
            name="uq_capture_search_run_result",
        ),
    )
    op.create_index(
        "ix_capture_search_run_results_rank",
        "capture_search_run_results",
        ["tenant_id", "search_run_id", "fit_score"],
    )
    op.create_index(
        "ix_capture_search_run_results_source",
        "capture_search_run_results",
        ["tenant_id", "search_run_id", "source_id"],
    )

    # The former model can only reconstruct the latest association for an ad. Preserve
    # everything that is still recoverable so existing environments keep their results.
    op.execute(
        """
        INSERT INTO capture_search_run_results (
            id, tenant_id, search_run_id, external_listing_id, source_id,
            fit_score, confidence_score, matched, tradeoffs, listing_snapshot, created_at
        )
        SELECT
            gen_random_uuid(), m.tenant_id, m.last_search_run_id, l.id, l.source_id,
            m.fit_score, m.confidence_score, m.matched, m.tradeoffs,
            jsonb_build_object(
                'id', l.id::text,
                'source_id', l.source_id,
                'source_domain', regexp_replace(
                    split_part(split_part(l.canonical_url, '://', 2), '/', 1),
                    '^www\\.',
                    ''
                ),
                'source_listing_id', l.source_listing_id,
                'canonical_url', l.canonical_url,
                'title', l.title,
                'description', l.description,
                'purpose', l.purpose,
                'property_type', l.property_type,
                'state', l.state,
                'city', l.city,
                'neighborhood', l.neighborhood,
                'price', l.price,
                'sale_price', l.sale_price,
                'rent_price', l.rent_price,
                'bedrooms', l.bedrooms,
                'bathrooms', l.bathrooms,
                'parking_spaces', l.parking_spaces,
                'area', l.area,
                'primary_image_url', l.primary_image_url,
                'advertiser_name', l.advertiser_name,
                'last_seen_at', l.last_seen_at
            ),
            m.created_at
        FROM demand_external_matches m
        JOIN external_listings l ON l.id = m.external_listing_id
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_capture_search_run_results_source", table_name="capture_search_run_results"
    )
    op.drop_index(
        "ix_capture_search_run_results_rank", table_name="capture_search_run_results"
    )
    op.drop_table("capture_search_run_results")
    op.drop_constraint(
        "ck_capture_search_run_sources_status",
        "capture_search_run_sources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_capture_search_run_sources_status",
        "capture_search_run_sources",
        "status IN ('queued', 'running', 'completed', 'failed', 'blocked')",
    )
    op.drop_constraint("ck_capture_jobs_status", "capture_jobs", type_="check")
    op.create_check_constraint(
        "ck_capture_jobs_status",
        "capture_jobs",
        "status IN ('queued', 'processing', 'retrying', 'completed', 'failed')",
    )
    op.drop_column("demand_external_matches", "saved_property_id")
    op.drop_index(
        "uq_capture_search_runs_cache_bucket", table_name="capture_search_runs"
    )
    for column in (
        "billing_reservation_key",
        "cancel_requested_at",
        "force_refresh",
        "matching_version",
        "catalog_version",
        "cache_expires_at",
        "cache_bucket",
        "cache_key",
        "requested_by_user_id",
    ):
        op.drop_column("capture_search_runs", column)
    op.drop_constraint("ck_lead_demands_price_range", "lead_demands", type_="check")
    op.drop_column("lead_demands", "state")
