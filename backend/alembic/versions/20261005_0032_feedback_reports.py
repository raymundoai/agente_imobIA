"""Feedback sent from inside the app to the platform team.

Revision ID: 20261005_0032
Revises: 20261005_0031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261005_0032"
down_revision = "20261005_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page", sa.Text()),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("status", sa.Text(), server_default="new", nullable=False),
        sa.Column("admin_note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('problem', 'suggestion', 'question', 'praise')",
            name=op.f("ck_feedback_reports_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'in_progress', 'resolved')", name=op.f("ck_feedback_reports_status")
        ),
    )
    op.create_index(
        "ix_feedback_reports_status_created", "feedback_reports", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_reports_status_created", table_name="feedback_reports")
    op.drop_table("feedback_reports")
