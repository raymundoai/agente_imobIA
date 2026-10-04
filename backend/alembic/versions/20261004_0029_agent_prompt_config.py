"""Platform-managed agent prompt versions and per-tenant instructions.

Revision ID: 20261004_0029
Revises: 20261004_0028
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261004_0029"
down_revision = "20261004_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("base_prompt", sa.Text()),
        sa.Column("chat_model", sa.Text()),
        sa.Column("reasoning_effort", sa.Text()),
        sa.Column("max_output_tokens", sa.Integer()),
        sa.Column("note", sa.Text()),
        sa.Column("created_by_email", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_agent_prompt_versions_created_at", "agent_prompt_versions", ["created_at"])
    op.create_table(
        "tenant_agent_overrides",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("extra_instructions", sa.Text(), nullable=False),
        sa.Column("updated_by_email", sa.Text()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("tenant_agent_overrides")
    op.drop_index("ix_agent_prompt_versions_created_at", table_name="agent_prompt_versions")
    op.drop_table("agent_prompt_versions")
