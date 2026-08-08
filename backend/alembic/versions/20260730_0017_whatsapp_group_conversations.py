"""Add WhatsApp group and participant metadata.

Revision ID: 20260730_0017
Revises: 20260725_0016
"""

import sqlalchemy as sa

from alembic import op

revision = "20260730_0017"
down_revision = "20260725_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("is_group", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("conversations", sa.Column("group_name", sa.Text()))
    op.add_column("messages", sa.Column("sender_external_id", sa.Text()))
    op.add_column("messages", sa.Column("sender_name", sa.Text()))
    op.create_index(
        "ix_conversations_tenant_external_contact",
        "conversations",
        ["tenant_id", "channel", "external_contact_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_tenant_external_contact", table_name="conversations")
    op.drop_column("messages", "sender_name")
    op.drop_column("messages", "sender_external_id")
    op.drop_column("conversations", "group_name")
    op.drop_column("conversations", "is_group")
