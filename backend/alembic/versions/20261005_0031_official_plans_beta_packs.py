"""Official plans (all with AI), beta pricing per tenant, self-service packs.

- Four public plans replace the earlier ones, which stay for history but leave the showcase.
  Each plan carries its beta price and the reference unit prices that packs are built from.
- A tenant can be put on beta pricing by the platform team.
- New accounts can wait for their first subscription ("pending", no allowance).
- Pack orders are one-off Asaas charges; the allowance is granted when the payment arrives.

Revision ID: 20261005_0031
Revises: 20261004_0030
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261005_0031"
down_revision = "20261004_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# code, name, price, attendances, searches, images, users, beta price, reference unit prices
PLANS = [
    ("essencial", "Essencial", 36900, 100, 50, 20, 3, 4900, (200, 40, 250), 1),
    ("profissional", "Profissional", 74900, 250, 150, 50, 5, 9900, (180, 35, 220), 2),
    ("avancado", "Avançado", 124900, 500, 300, 100, 10, 17900, (160, 30, 190), 3),
    ("escala", "Escala", 194900, 1000, 600, 200, 20, 34900, (130, 25, 140), 4),
]
OLD_PUBLIC = ("operacao", "ia_essencial", "ia_profissional", "ia_escala")
STATUS_WITH_PENDING = "status IN ('pilot', 'trial', 'pending', 'active', 'past_due', 'cancelled')"
STATUS_WITHOUT_PENDING = "status IN ('pilot', 'trial', 'active', 'past_due', 'cancelled')"


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_tenant_commercial_subscriptions_status"),
        "tenant_commercial_subscriptions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_tenant_commercial_subscriptions_status"),
        "tenant_commercial_subscriptions",
        STATUS_WITH_PENDING,
    )
    op.add_column(
        "tenant_commercial_subscriptions",
        sa.Column("beta_pricing", sa.Boolean(), server_default="false", nullable=False),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE commercial_plans SET is_public = false WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": list(OLD_PUBLIC)},
    )
    # Placeholder for accounts that have not subscribed yet: no allowance, never shown.
    bind.execute(
        sa.text(
            "INSERT INTO commercial_plans (id, code, name, version, monthly_price_cents, currency, "
            "ai_attendances, property_searches, image_optimizations, max_users, is_current, "
            "is_public, extra) VALUES (gen_random_uuid(), 'sem_plano', 'Sem plano', 1, 0, 'BRL', "
            "0, 0, 0, 3, true, false, '{}'::jsonb)"
        )
    )
    for code, name, price, att, srch, img, users, beta, refs, order in PLANS:
        extra = {
            "beta_price_cents": beta,
            "display_order": order,
            "reference_unit_cents": {
                "ai_attendance": refs[0],
                "property_search_standard": refs[1],
                "image_optimization": refs[2],
            },
        }
        bind.execute(
            sa.text(
                "INSERT INTO commercial_plans (id, code, name, version, monthly_price_cents, "
                "currency, ai_attendances, property_searches, image_optimizations, max_users, "
                "is_current, is_public, extra) VALUES (gen_random_uuid(), :code, :name, 1, "
                ":price, 'BRL', :att, :srch, :img, :users, true, true, CAST(:extra AS jsonb))"
            ),
            {
                "code": code,
                "name": name,
                "price": price,
                "att": att,
                "srch": srch,
                "img": img,
                "users": users,
                "extra": json.dumps(extra),
            },
        )

    op.create_table(
        "asaas_pack_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("value_cents", sa.Integer(), nullable=False),
        sa.Column("plan_code", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("external_reference", sa.Text(), nullable=False, unique=True),
        sa.Column("provider_payment_id", sa.Text(), unique=True),
        sa.Column("invoice_url", sa.Text()),
        sa.Column("status", sa.Text(), server_default="creating", nullable=False),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('creating', 'pending_payment', 'paid', 'failed', 'cancelled')",
            name=op.f("ck_asaas_pack_orders_status"),
        ),
        sa.CheckConstraint("units > 0", name=op.f("ck_asaas_pack_orders_units")),
        sa.CheckConstraint("value_cents >= 500", name=op.f("ck_asaas_pack_orders_value")),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name=op.f("uq_asaas_pack_orders_key")),
    )
    op.create_index(
        "ix_asaas_pack_orders_tenant_created", "asaas_pack_orders", ["tenant_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_asaas_pack_orders_tenant_created", table_name="asaas_pack_orders")
    op.drop_table("asaas_pack_orders")
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM commercial_plans WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": [plan[0] for plan in PLANS] + ["sem_plano"]},
    )
    bind.execute(
        sa.text("UPDATE commercial_plans SET is_public = true WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": list(OLD_PUBLIC)},
    )
    op.drop_column("tenant_commercial_subscriptions", "beta_pricing")
    op.drop_constraint(
        op.f("ck_tenant_commercial_subscriptions_status"),
        "tenant_commercial_subscriptions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_tenant_commercial_subscriptions_status"),
        "tenant_commercial_subscriptions",
        STATUS_WITHOUT_PENDING,
    )
