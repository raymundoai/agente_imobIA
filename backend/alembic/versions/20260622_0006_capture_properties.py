"""Create properties and capture demand matches.

Revision ID: 20260622_0006
Revises: 20260622_0005
Create Date: 2026-06-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260622_0006"
down_revision = "20260622_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_lead_demands_tenant_id_id",
        "lead_demands",
        ["tenant_id", "id"],
    )
    op.create_table(
        "properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("neighborhood", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("property_type", sa.Text(), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("parking_spaces", sa.Integer(), nullable=True),
        sa.Column("area", sa.Integer(), nullable=True),
        sa.Column(
            "images",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("advertiser_name", sa.Text(), nullable=True),
        sa.Column("advertiser_phone", sa.Text(), nullable=True),
        sa.Column("via_extension", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("duplicate_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('buy', 'rent') OR purpose IS NULL",
            name=op.f("ck_properties_purpose"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_properties_tenant_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_properties")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_properties_tenant_id_id"),
    )
    op.create_index("ix_properties_tenant_city", "properties", ["tenant_id", "city"])
    op.create_index(
        "ix_properties_tenant_filters",
        "properties",
        ["tenant_id", "purpose", "property_type", "city"],
    )
    op.create_index(
        "uq_properties_tenant_source_url",
        "properties",
        ["tenant_id", "source_url"],
        unique=True,
        postgresql_where=sa.text("source_url IS NOT NULL"),
    )
    op.create_index(
        "uq_properties_tenant_content_hash",
        "properties",
        ["tenant_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )

    op.create_table(
        "property_demand_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_score", sa.Integer(), server_default="100", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "property_id"],
            ["properties.tenant_id", "properties.id"],
            name="fk_property_matches_tenant_property",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "demand_id"],
            ["lead_demands.tenant_id", "lead_demands.id"],
            name="fk_property_matches_tenant_demand",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_demand_matches")),
        sa.UniqueConstraint(
            "tenant_id",
            "property_id",
            "demand_id",
            name="uq_property_demand_match",
        ),
    )
    op.create_index(
        "ix_property_matches_tenant_demand",
        "property_demand_matches",
        ["tenant_id", "demand_id"],
    )
    op.create_index(
        "ix_property_matches_tenant_property",
        "property_demand_matches",
        ["tenant_id", "property_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_property_matches_tenant_property", table_name="property_demand_matches")
    op.drop_index("ix_property_matches_tenant_demand", table_name="property_demand_matches")
    op.drop_table("property_demand_matches")
    op.drop_index("uq_properties_tenant_content_hash", table_name="properties")
    op.drop_index("uq_properties_tenant_source_url", table_name="properties")
    op.drop_index("ix_properties_tenant_filters", table_name="properties")
    op.drop_index("ix_properties_tenant_city", table_name="properties")
    op.drop_table("properties")
    op.drop_constraint("uq_lead_demands_tenant_id_id", "lead_demands", type_="unique")
