"""Add tenant credit accounts and immutable usage ledger.

Revision ID: 20260725_0011
Revises: 20260712_0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260725_0011"
down_revision = "20260712_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_accounts",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("balance_credits", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("enforcement_mode", sa.Text(), server_default="meter_only", nullable=False),
        sa.Column("unlimited_messages", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "enforcement_mode IN ('meter_only', 'enforce')",
            name=op.f("ck_credit_accounts_credit_accounts_enforcement_mode"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_credit_accounts_tenant_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_credit_accounts")),
    )
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("delta_credits", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("provider_cost_usd", sa.Numeric(14, 8), server_default="0", nullable=False),
        sa.Column("retail_cost_usd", sa.Numeric(14, 8), server_default="0", nullable=False),
        sa.Column("reference_id", sa.UUID()),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_by", sa.UUID()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_credit_ledger_tenant_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_ledger")),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name=op.f("uq_credit_ledger_tenant_idempotency"),
        ),
    )
    op.create_index(
        "ix_credit_ledger_tenant_created", "credit_ledger", ["tenant_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_tenant_created", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_table("credit_accounts")
