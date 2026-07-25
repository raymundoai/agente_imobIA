"""Add operational lead agent state.

Revision ID: 20260712_0007
Revises: 20260622_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260712_0007"
down_revision: str | None = "20260622_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("current_agent", sa.Text(), server_default="leads", nullable=False),
    )
    op.add_column(
        "ai_audit_logs",
        sa.Column("agent_key", sa.Text(), server_default="leads", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("ai_audit_logs", "agent_key")
    op.drop_column("conversations", "current_agent")
