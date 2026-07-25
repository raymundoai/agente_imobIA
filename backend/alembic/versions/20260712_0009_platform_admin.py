"""Add isolated platform administrators.

Revision ID: 20260712_0009
Revises: 20260712_0008
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260712_0009"
down_revision = "20260712_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name=op.f("ck_platform_users_status")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_platform_users_email", "platform_users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_table("platform_users")
