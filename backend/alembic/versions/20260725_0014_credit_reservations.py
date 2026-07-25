"""Add transactional credit reservations.

Revision ID: 20260725_0014
Revises: 20260725_0013
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260725_0014"
down_revision = "20260725_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credit_accounts",
        sa.Column("reserved_credits", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.create_table(
        "credit_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="reserved", nullable=False),
        sa.Column("reserved_credits", sa.BigInteger(), nullable=False),
        sa.Column("actual_credits", sa.BigInteger()),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('reserved', 'started', 'settled', 'released')",
            name=op.f("ck_credit_reservations_credit_reservations_status"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_credit_reservations_tenant_idempotency",
        ),
    )
    op.create_index(
        "ix_credit_reservations_status_expires",
        "credit_reservations",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("credit_reservations")
    op.drop_column("credit_accounts", "reserved_credits")
