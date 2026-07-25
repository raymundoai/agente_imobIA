"""Add persistent message jobs.

Revision ID: 20260725_0013
Revises: 20260725_0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260725_0013"
down_revision = "20260725_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_messages_tenant_id_id", "messages", ["tenant_id", "id"])
    op.create_table(
        "message_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="received", nullable=False),
        sa.Column("stage", sa.Text(), server_default="generation", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("send_to_channel", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("response_text", sa.Text()),
        sa.Column("outbound_message_id", postgresql.UUID(as_uuid=True)),
        sa.Column("result", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('received', 'processing', 'delivery_pending', 'sent', "
            "'failed', 'retrying', 'delivery_unknown')",
            name=op.f("ck_message_jobs_status"),
        ),
        sa.CheckConstraint(
            "stage IN ('generation', 'delivery')",
            name=op.f("ck_message_jobs_stage"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_message_jobs_tenant_message",
        "message_jobs",
        ["tenant_id", "message_id"],
        unique=True,
    )
    op.create_index(
        "ix_message_jobs_claim", "message_jobs", ["status", "available_at", "created_at"]
    )
    op.create_index(
        "ix_message_jobs_tenant_status", "message_jobs", ["tenant_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("message_jobs")
    op.drop_constraint("uq_messages_tenant_id_id", "messages", type_="unique")
