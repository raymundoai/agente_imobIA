"""Create maintenance tickets.

Revision ID: 20260622_0005
Revises: 20260622_0004
Create Date: 2026-06-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260622_0005"
down_revision = "20260622_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("property_reference", sa.Text(), nullable=True),
        sa.Column("issue_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("urgency", sa.Text(), server_default="medium", nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "attachments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "urgency IN ('low', 'medium', 'high', 'critical')",
            name=op.f("ck_maintenance_tickets_urgency"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved')",
            name=op.f("ck_maintenance_tickets_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_maintenance_tickets_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_maintenance_tickets_tenant_conversation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_maintenance_tickets_tenant_assigned_user",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_maintenance_tickets")),
    )
    op.create_index(
        "ix_maintenance_tickets_tenant_status",
        "maintenance_tickets",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_maintenance_tickets_tenant_urgency",
        "maintenance_tickets",
        ["tenant_id", "urgency"],
    )
    op.create_index(
        "ix_maintenance_tickets_tenant_created",
        "maintenance_tickets",
        ["tenant_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_maintenance_tickets_tenant_conversation",
        "maintenance_tickets",
        ["tenant_id", "conversation_id"],
        postgresql_where=sa.text("conversation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_maintenance_tickets_tenant_conversation", table_name="maintenance_tickets")
    op.drop_index("ix_maintenance_tickets_tenant_created", table_name="maintenance_tickets")
    op.drop_index("ix_maintenance_tickets_tenant_urgency", table_name="maintenance_tickets")
    op.drop_index("ix_maintenance_tickets_tenant_status", table_name="maintenance_tickets")
    op.drop_table("maintenance_tickets")
