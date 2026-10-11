"""Beta broker plan, commercial segment, and consolidated monthly invoices.

Revision ID: 20261011_0034
Revises: 20261006_0033
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261011_0034"
down_revision = "20261006_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenant_commercial_subscriptions", sa.Column("commercial_segment", sa.Text()))
    op.create_check_constraint(
        "ck_tenant_commercial_subscriptions_segment",
        "tenant_commercial_subscriptions",
        "commercial_segment IS NULL OR commercial_segment IN ('broker', 'agency')",
    )
    # Existing accounts keep their contracted plan; their commercial category can be set later.
    op.get_bind().execute(
        sa.text(
            "INSERT INTO commercial_plans (id, code, name, version, monthly_price_cents, "
            "currency, ai_attendances, property_searches, image_optimizations, max_users, "
            "is_current, is_public, extra) VALUES (gen_random_uuid(), 'corretor_beta', "
            "'Corretor beta', 1, 5990, 'BRL', 0, 20, 0, 2, true, true, "
            "CAST(:extra AS jsonb))"
        ),
        {
            "extra": json.dumps(
                {
                    "audience": "broker",
                    "beta_only": True,
                    "postpaid_unit_cents": {"ai_attendance": 290, "image_optimization": 250},
                    "image_pack": {"units": 15, "price_cents": 3000},
                }
            )
        },
    )
    op.create_table(
        "broker_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commercial_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider_customer_id", sa.Text(), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), unique=True),
        sa.Column("external_reference", sa.Text(), nullable=False, unique=True),
        sa.Column("invoice_url", sa.Text()),
        sa.Column("billing_type", sa.Text(), nullable=False),
        sa.Column("cycle_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("base_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default="creating", nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "cycle_start", name="uq_broker_invoices_tenant_cycle"),
        sa.CheckConstraint("cycle_end > cycle_start", name="ck_broker_invoices_cycle"),
        sa.CheckConstraint(
            "total_cents >= base_cents AND base_cents >= 0", name="ck_broker_invoices_amount"
        ),
        sa.CheckConstraint(
            "status IN ('creating', 'pending_payment', 'paid', 'past_due', 'failed', 'cancelled')",
            name="ck_broker_invoices_status",
        ),
    )
    op.create_index(
        "ix_broker_invoices_tenant_created", "broker_invoices", ["tenant_id", "created_at"]
    )
    op.create_table(
        "broker_invoice_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "usage_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commercial_usage_events.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "units > 0 AND unit_price_cents > 0", name="ck_broker_invoice_usage_positive"
        ),
    )


def downgrade() -> None:
    op.drop_table("broker_invoice_usage")
    op.drop_index("ix_broker_invoices_tenant_created", table_name="broker_invoices")
    op.drop_table("broker_invoices")
    op.execute("DELETE FROM commercial_plans WHERE code = 'corretor_beta'")
    op.drop_constraint(
        "ck_tenant_commercial_subscriptions_segment",
        "tenant_commercial_subscriptions",
        type_="check",
    )
    op.drop_column("tenant_commercial_subscriptions", "commercial_segment")
