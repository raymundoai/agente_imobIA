"""Expand properties and add contacts.

Revision ID: 20260712_0008
Revises: 20260712_0007
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260712_0008"
down_revision = "20260712_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_properties_purpose"), "properties", type_="check")
    op.create_check_constraint(
        op.f("ck_properties_purpose"),
        "properties",
        "purpose IN ('buy', 'rent', 'both') OR purpose IS NULL",
    )
    columns = [
        sa.Column("sale_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("rent_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("category", sa.Text(), server_default="residential", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("listing_code", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("suites", sa.Integer(), nullable=True),
        sa.Column("bathrooms", sa.Integer(), nullable=True),
        sa.Column("land_area", sa.Integer(), nullable=True),
        sa.Column(
            "address",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    ]
    for column in columns:
        op.add_column("properties", column)
    op.create_check_constraint(
        op.f("ck_properties_category"),
        "properties",
        "category IN ('residential', 'commercial', 'mixed')",
    )
    op.create_check_constraint(
        op.f("ck_properties_status"),
        "properties",
        "status IN ('draft', 'active', 'inactive')",
    )
    op.create_index(
        "uq_properties_tenant_listing_code",
        "properties",
        ["tenant_id", "listing_code"],
        unique=True,
        postgresql_where=sa.text("listing_code IS NOT NULL"),
    )

    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("interest", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('lead', 'tenant', 'owner', 'client')",
            name=op.f("ck_contacts_kind"),
        ),
        sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f("ck_contacts_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_contacts_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "phone", name="uq_contacts_tenant_phone"),
    )
    op.create_index("ix_contacts_tenant_kind", "contacts", ["tenant_id", "kind"])
    op.create_index("ix_contacts_tenant_name", "contacts", ["tenant_id", "name"])


def downgrade() -> None:
    op.drop_table("contacts")
    op.drop_index("uq_properties_tenant_listing_code", table_name="properties")
    op.drop_constraint(op.f("ck_properties_status"), "properties", type_="check")
    op.drop_constraint(op.f("ck_properties_category"), "properties", type_="check")
    for name in [
        "details",
        "address",
        "land_area",
        "bathrooms",
        "suites",
        "description",
        "listing_code",
        "status",
        "category",
        "rent_price",
        "sale_price",
    ]:
        op.drop_column("properties", name)
    op.drop_constraint(op.f("ck_properties_purpose"), "properties", type_="check")
    op.create_check_constraint(
        op.f("ck_properties_purpose"),
        "properties",
        "purpose IN ('buy', 'rent') OR purpose IS NULL",
    )
