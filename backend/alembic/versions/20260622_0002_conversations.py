"""Create conversations, messages, and usage records.

Revision ID: 20260622_0002
Revises: 20260622_0001
Create Date: 2026-06-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260622_0002"
down_revision = "20260622_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_users_tenant_id_id", "users", ["tenant_id", "id"])
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), server_default="whatsapp", nullable=False),
        sa.Column("external_contact_id", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("mode", sa.Text(), server_default="ai", nullable=False),
        sa.Column("current_intent", sa.Text(), nullable=True),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("channel IN ('whatsapp')", name=op.f("ck_conversations_channel")),
        sa.CheckConstraint(
            "status IN ('open', 'waiting_human', 'closed')",
            name=op.f("ck_conversations_status"),
        ),
        sa.CheckConstraint("mode IN ('ai', 'human')", name=op.f("ck_conversations_mode")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_conversations_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_conversations_tenant_assigned_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id_id"),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index(
        "ix_conversations_tenant_status_last_message",
        "conversations",
        ["tenant_id", "status", sa.text("last_message_at DESC")],
    )
    op.create_index(
        "uq_conversations_active_phone",
        "conversations",
        ["tenant_id", "channel", "phone"],
        unique=True,
        postgresql_where=sa.text("status <> 'closed'"),
    )
    op.create_index(
        "ix_conversations_tenant_assigned_user",
        "conversations",
        ["tenant_id", "assigned_user_id"],
        postgresql_where=sa.text("assigned_user_id IS NOT NULL"),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), server_default="whatsapp", nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("author_type", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "attachments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("external_message_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound')", name=op.f("ck_messages_direction")
        ),
        sa.CheckConstraint(
            "author_type IN ('customer', 'ai', 'human', 'system')",
            name=op.f("ck_messages_author_type"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_messages_tenant_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index(
        "ix_messages_tenant_conversation_created",
        "messages",
        ["tenant_id", "conversation_id", "created_at"],
    )
    op.create_index(
        "uq_messages_tenant_channel_external_id",
        "messages",
        ["tenant_id", "channel", "external_message_id"],
        unique=True,
        postgresql_where=sa.text("external_message_id IS NOT NULL"),
    )

    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("related_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_usage_records_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_usage_records_tenant_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usage_records"),
    )
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"])
    op.create_index(
        "ix_usage_records_tenant_type_created",
        "usage_records",
        ["tenant_id", "type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_records_tenant_type_created", table_name="usage_records")
    op.drop_index("ix_usage_records_tenant_id", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index("uq_messages_tenant_channel_external_id", table_name="messages")
    op.drop_index("ix_messages_tenant_conversation_created", table_name="messages")
    op.drop_index("ix_messages_tenant_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_tenant_assigned_user", table_name="conversations")
    op.drop_index("uq_conversations_active_phone", table_name="conversations")
    op.drop_index("ix_conversations_tenant_status_last_message", table_name="conversations")
    op.drop_index("ix_conversations_tenant_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_constraint("uq_users_tenant_id_id", "users", type_="unique")
