"""Limited, manually approved broker beta test access.

Revision ID: 20261021_0036
Revises: 20261021_0035
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261021_0036"
down_revision = "20261021_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_test_accesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO commercial_plans
                (id, code, name, version, monthly_price_cents, currency,
                 ai_attendances, property_searches, image_optimizations,
                 max_users, is_current, is_public, extra)
            VALUES
                (gen_random_uuid(), 'corretor_teste_15d', 'Teste beta de 15 dias', 1, 0, 'BRL',
                 10, 20, 10, 2, true, false, CAST(:extra AS jsonb))
            """
        ),
        {"extra": json.dumps({"audience": "broker", "manual_test_access": True})},
    )


def downgrade() -> None:
    op.drop_table("broker_test_accesses")
    op.execute(sa.text("DELETE FROM commercial_plans WHERE code = 'corretor_teste_15d'"))
