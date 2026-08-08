"""Harden tenant user management and add secure invitations.

Revision ID: 20260804_0018
Revises: 20260730_0017
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260804_0018"
down_revision = "20260730_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_users_status"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_status"),
        "users",
        "status IN ('active', 'inactive', 'invited')",
    )
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("invitation_token_hash", sa.Text()))
    op.add_column("users", sa.Column("invitation_expires_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("invited_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_users_invitation_token_hash", "users", ["invitation_token_hash"]
    )

    op.create_table(
        "user_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "changes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_user_audit_tenant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_user_audit_actor", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], name="fk_user_audit_target", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_audit_logs"),
    )
    op.create_index(
        "ix_user_audit_tenant_created",
        "user_audit_logs",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_audit_tenant_created", table_name="user_audit_logs")
    op.drop_table("user_audit_logs")
    op.drop_constraint("uq_users_invitation_token_hash", "users", type_="unique")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "invited_at")
    op.drop_column("users", "invitation_expires_at")
    op.drop_column("users", "invitation_token_hash")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "session_version")
    op.drop_constraint(op.f("ck_users_status"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_status"), "users", "status IN ('active', 'inactive')")
