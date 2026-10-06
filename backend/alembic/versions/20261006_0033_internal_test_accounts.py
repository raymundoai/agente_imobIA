"""Internal test accounts: unlimited use and a private R$ 5,00 plan to validate payments.

- The platform team can mark a tenant as an internal test account (the team's own accounts).
- Such accounts run metered but never blocked, and their billing page offers only the private
  test plan, a real Asaas charge of R$ 5,00 (the PIX minimum) to validate the payment flow.

Revision ID: 20261006_0033
Revises: 20261005_0032
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20261006_0033"
down_revision = "20261005_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEST_PLAN_CODE = "teste_pagamento"


def upgrade() -> None:
    op.add_column(
        "tenant_commercial_subscriptions",
        sa.Column("internal_test", sa.Boolean(), server_default="false", nullable=False),
    )
    op.get_bind().execute(
        sa.text(
            "INSERT INTO commercial_plans (id, code, name, version, monthly_price_cents, currency, "
            "ai_attendances, property_searches, image_optimizations, max_users, is_current, "
            "is_public, extra) VALUES (gen_random_uuid(), :code, 'Teste de pagamento', 1, 500, "
            "'BRL', 1000, 1000, 200, 20, true, false, CAST(:extra AS jsonb))"
        ),
        {"code": TEST_PLAN_CODE, "extra": json.dumps({"internal_test": True, "display_order": 0})},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM commercial_plans WHERE code = :code AND id NOT IN "
            "(SELECT plan_id FROM tenant_commercial_subscriptions) AND id NOT IN "
            "(SELECT plan_id FROM asaas_subscriptions)"
        ),
        {"code": TEST_PLAN_CODE},
    )
    op.drop_column("tenant_commercial_subscriptions", "internal_test")
