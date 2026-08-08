"""Add immutable master user and safe profile deletion.

Revision ID: 20260804_0019
Revises: 20260804_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260804_0019"
down_revision = "20260804_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_master", sa.Boolean(), server_default="false", nullable=False),
    )
    op.execute(
        """
        WITH first_users AS (
            SELECT DISTINCT ON (tenant_id) id
            FROM users
            ORDER BY tenant_id, created_at, id
        )
        UPDATE users
        SET is_master = true, role = 'admin', status = 'active'
        WHERE id IN (SELECT id FROM first_users)
        """
    )
    op.create_index(
        "uq_users_one_master_per_tenant",
        "users",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_master"),
    )
    op.create_check_constraint(
        op.f("ck_users_master_is_active_admin"),
        "users",
        "NOT is_master OR (role = 'admin' AND status = 'active')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_master_is_active_admin"), "users", type_="check")
    op.drop_index("uq_users_one_master_per_tenant", table_name="users")
    op.drop_column("users", "is_master")
