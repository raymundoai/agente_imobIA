"""Add the free trial plan and trial status for self-service signup.

Revision ID: 20261002_0026
Revises: 20260915_0025
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20261002_0026"
down_revision = "20260915_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIAL_PLAN_ID = "00000000-0000-4000-8000-000000000006"


def upgrade() -> None:
    op.add_column(
        "tenant_commercial_subscriptions",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
    )
    # 0023 created this constraint under a truncated, hashed name; find it by definition.
    _drop_status_check()
    op.create_check_constraint(
        op.f("ck_tenant_commercial_subscriptions_status"),
        "tenant_commercial_subscriptions",
        "status IN ('pilot', 'trial', 'active', 'past_due', 'cancelled')",
    )
    op.execute(
        sa.text(
            """
            INSERT INTO commercial_plans
                (id, code, name, version, monthly_price_cents, currency,
                 ai_attendances, property_searches, image_optimizations,
                 max_users, is_current, is_public, extra)
            VALUES
                (CAST(:id AS uuid), 'teste_gratis', 'Teste grátis', 1, 0, 'BRL',
                 30, 30, 5, 3, true, false, '{}'::jsonb)
            ON CONFLICT (id) DO UPDATE SET is_current = true
            """
        ).bindparams(id=TRIAL_PLAN_ID)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE tenant_commercial_subscriptions
            SET status = 'cancelled'
            WHERE status = 'trial'
            """
        )
    )
    _drop_status_check()
    op.create_check_constraint(
        op.f("ck_tenant_commercial_subscriptions_status"),
        "tenant_commercial_subscriptions",
        "status IN ('pilot', 'active', 'past_due', 'cancelled')",
    )
    op.drop_column("tenant_commercial_subscriptions", "trial_ends_at")
    # Kept for history (subscriptions may reference it) but no longer offered.
    op.execute(
        sa.text(
            "UPDATE commercial_plans SET is_current = false WHERE id = CAST(:id AS uuid)"
        ).bindparams(id=TRIAL_PLAN_ID)
    )


def _drop_status_check() -> None:
    op.execute(
        """
        DO $$
        DECLARE constraint_name text;
        BEGIN
            FOR constraint_name IN
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'tenant_commercial_subscriptions'::regclass
                  AND contype = 'c'
                  AND pg_get_constraintdef(oid) LIKE '%status%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE tenant_commercial_subscriptions DROP CONSTRAINT %I',
                    constraint_name
                );
            END LOOP;
        END $$;
        """
    )
