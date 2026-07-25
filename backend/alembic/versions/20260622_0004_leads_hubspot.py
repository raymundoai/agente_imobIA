"""Create lead demands for HubSpot SDR sync.

Revision ID: 20260622_0004
Revises: 20260622_0003
Create Date: 2026-06-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260622_0004"
down_revision = "20260622_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_demands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("property_type", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column(
            "neighborhoods",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("price_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("parking_spaces", sa.Integer(), nullable=True),
        sa.Column("min_area", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("responsible_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("crm_contact_id", sa.Text(), nullable=True),
        sa.Column("crm_deal_id", sa.Text(), nullable=True),
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
            name=op.f("ck_lead_demands_purpose"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'qualified', 'in_progress', 'closed')",
            name=op.f("ck_lead_demands_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_lead_demands_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "responsible_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_lead_demands_tenant_responsible_user",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_demands")),
    )
    op.create_index("ix_lead_demands_tenant_status", "lead_demands", ["tenant_id", "status"])
    op.create_index("ix_lead_demands_tenant_phone", "lead_demands", ["tenant_id", "phone"])
    op.create_index(
        "ix_lead_demands_tenant_created",
        "lead_demands",
        ["tenant_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "uq_lead_demands_open_phone",
        "lead_demands",
        ["tenant_id", "phone"],
        unique=True,
        postgresql_where=sa.text("status <> 'closed'"),
    )
    op.create_index(
        "ix_lead_demands_tenant_crm_contact",
        "lead_demands",
        ["tenant_id", "crm_contact_id"],
        postgresql_where=sa.text("crm_contact_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_lead_demands_tenant_crm_contact", table_name="lead_demands")
    op.drop_index("uq_lead_demands_open_phone", table_name="lead_demands")
    op.drop_index("ix_lead_demands_tenant_created", table_name="lead_demands")
    op.drop_index("ix_lead_demands_tenant_phone", table_name="lead_demands")
    op.drop_index("ix_lead_demands_tenant_status", table_name="lead_demands")
    op.drop_table("lead_demands")
