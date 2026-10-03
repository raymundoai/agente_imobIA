"""Add the ImmobIA network: shared listings, member terms and partnership requests.

Revision ID: 20261002_0027
Revises: 20261002_0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261002_0027"
down_revision = "20261002_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("network_shared", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("properties", sa.Column("network_shared_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_properties_network_shared",
        "properties",
        ["tenant_id"],
        postgresql_where=sa.text("network_shared"),
    )
    op.create_table(
        "network_memberships",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("terms_version", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_commission_percent", sa.Integer(), nullable=False),
        sa.Column("contact_name", sa.Text(), nullable=False),
        sa.Column("contact_phone", sa.Text(), nullable=False),
        sa.Column("contact_email", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "partner_commission_percent BETWEEN 1 AND 99",
            name=op.f("ck_network_memberships_commission"),
        ),
    )
    op.create_table(
        "network_partnership_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owner_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requester_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True)),
        sa.Column("message", sa.Text()),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        # Terms agreed when the request was made, so later changes do not rewrite them.
        sa.Column("partner_commission_percent", sa.Integer(), nullable=False),
        sa.Column("property_title", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["owner_tenant_id", "property_id"],
            ["properties.tenant_id", "properties.id"],
            ondelete="CASCADE",
            name=op.f("fk_network_partnership_requests_owner_property"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')",
            name=op.f("ck_network_partnership_requests_status"),
        ),
        sa.CheckConstraint(
            "owner_tenant_id <> requester_tenant_id",
            name=op.f("ck_network_partnership_requests_distinct_tenants"),
        ),
    )
    op.create_index(
        "uq_network_partnership_requests_open",
        "network_partnership_requests",
        ["property_id", "requester_tenant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'accepted')"),
    )
    op.create_index(
        "ix_network_partnership_requests_owner",
        "network_partnership_requests",
        ["owner_tenant_id", "status", "created_at"],
    )
    op.create_index(
        "ix_network_partnership_requests_requester",
        "network_partnership_requests",
        ["requester_tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_network_partnership_requests_requester", table_name="network_partnership_requests"
    )
    op.drop_index(
        "ix_network_partnership_requests_owner", table_name="network_partnership_requests"
    )
    op.drop_index("uq_network_partnership_requests_open", table_name="network_partnership_requests")
    op.drop_table("network_partnership_requests")
    op.drop_table("network_memberships")
    op.drop_index("ix_properties_network_shared", table_name="properties")
    op.drop_column("properties", "network_shared_at")
    op.drop_column("properties", "network_shared")
