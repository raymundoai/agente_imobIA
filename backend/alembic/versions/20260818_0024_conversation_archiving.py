"""Add reversible conversation archiving.

Revision ID: 20260818_0024
Revises: 20260814_0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260818_0024"
down_revision = "20260814_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_tenant_archived_by_user",
        "conversations",
        "users",
        ["tenant_id", "archived_by_user_id"],
        ["tenant_id", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_archived_last_message",
        "conversations",
        ["tenant_id", "archived_at", sa.text("last_message_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_tenant_archived_last_message", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_tenant_archived_by_user", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "archived_by_user_id")
    op.drop_column("conversations", "archived_at")
