"""Add Asaas customer, subscription and webhook reconciliation records.

Revision ID: 20260915_0025
Revises: 20260818_0024
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260915_0025"
down_revision = "20260818_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asaas_customer_links",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider_customer_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "asaas_subscriptions",
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
        sa.Column("provider_subscription_id", sa.Text()),
        sa.Column("provider_payment_id", sa.Text()),
        sa.Column("external_reference", sa.Text(), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("billing_type", sa.Text(), nullable=False),
        sa.Column("value_cents", sa.Integer(), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("enforcement_mode", sa.Text(), server_default="enforce", nullable=False),
        sa.Column("status", sa.Text(), server_default="creating", nullable=False),
        sa.Column("invoice_url", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('creating', 'pending_payment', 'active', 'past_due', "
            "'cancelled', 'failed')",
            name="ck_asaas_subscriptions_status",
        ),
        sa.CheckConstraint(
            "billing_type IN ('UNDEFINED', 'BOLETO', 'CREDIT_CARD', 'PIX')",
            name="ck_asaas_subscriptions_billing_type",
        ),
        sa.CheckConstraint(
            "enforcement_mode IN ('meter_only', 'enforce')",
            name="ck_asaas_subscriptions_enforcement",
        ),
        sa.CheckConstraint("value_cents > 0", name="ck_asaas_subscriptions_value"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_asaas_subscriptions_tenant_key"
        ),
        sa.UniqueConstraint("provider_subscription_id", name="uq_asaas_subscriptions_provider_id"),
    )
    op.create_index(
        "ix_asaas_subscriptions_tenant_created",
        "asaas_subscriptions",
        ["tenant_id", "created_at"],
    )
    op.create_table(
        "asaas_webhook_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("environment_url", sa.Text(), nullable=False, unique=True),
        sa.Column("provider_webhook_id", sa.Text(), nullable=False, unique=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("notification_email", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "asaas_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asaas_subscriptions.id", ondelete="SET NULL"),
        ),
        sa.Column("payload", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("outcome", sa.Text(), server_default="received", nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("provider_event_id", name="uq_asaas_webhook_events_provider_id"),
    )
    op.create_index(
        "ix_asaas_webhook_events_subscription_received",
        "asaas_webhook_events",
        ["subscription_id", "received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asaas_webhook_events_subscription_received", table_name="asaas_webhook_events"
    )
    op.drop_table("asaas_webhook_events")
    op.drop_table("asaas_webhook_configs")
    op.drop_index("ix_asaas_subscriptions_tenant_created", table_name="asaas_subscriptions")
    op.drop_table("asaas_subscriptions")
    op.drop_table("asaas_customer_links")
