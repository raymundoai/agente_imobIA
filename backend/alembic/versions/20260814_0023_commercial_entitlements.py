"""Add commercial plans, entitlements and 24-hour AI attendances.

Revision ID: 20260814_0023
Revises: 20260813_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260814_0023"
down_revision = "20260813_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PILOT_PLAN_ID = "00000000-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.create_table(
        "commercial_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("monthly_price_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.Text(), server_default="BRL", nullable=False),
        sa.Column("ai_attendances", sa.Integer(), server_default="0", nullable=False),
        sa.Column("property_searches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("image_optimizations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_users", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("monthly_price_cents >= 0", name="ck_commercial_plans_price"),
        sa.CheckConstraint("max_users > 0", name="ck_commercial_plans_max_users"),
        sa.UniqueConstraint("code", "version", name="uq_commercial_plans_code_version"),
    )
    op.create_index(
        "uq_commercial_plans_current_code",
        "commercial_plans",
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "commercial_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer()),
        sa.Column("currency", sa.Text(), server_default="BRL", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("units > 0", name="ck_commercial_packs_units"),
        sa.CheckConstraint(
            "resource IN ('ai_attendance', 'property_search_standard', "
            "'property_search_ai', 'image_optimization')",
            name="ck_commercial_packs_resource",
        ),
        sa.CheckConstraint(
            "price_cents IS NULL OR price_cents >= 0", name="ck_commercial_packs_price"
        ),
        sa.UniqueConstraint("code", name="uq_commercial_packs_code"),
    )
    op.create_table(
        "tenant_commercial_subscriptions",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commercial_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="pilot", nullable=False),
        sa.Column("enforcement_mode", sa.Text(), server_default="meter_only", nullable=False),
        sa.Column("cycle_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pilot', 'active', 'past_due', 'cancelled')",
            name="ck_tenant_commercial_subscriptions_status",
        ),
        sa.CheckConstraint(
            "enforcement_mode IN ('meter_only', 'enforce')",
            name="ck_tenant_commercial_subscriptions_enforcement",
        ),
        sa.CheckConstraint(
            "cycle_ends_at > cycle_started_at",
            name="ck_tenant_commercial_subscriptions_cycle",
        ),
    )
    op.create_table(
        "commercial_entitlement_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("consumed_units", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_units", sa.Integer(), server_default="0", nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text()),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity > 0", name="ck_commercial_grants_quantity"),
        sa.CheckConstraint("consumed_units >= 0", name="ck_commercial_grants_consumed"),
        sa.CheckConstraint("reserved_units >= 0", name="ck_commercial_grants_reserved"),
        sa.CheckConstraint(
            "consumed_units + reserved_units <= quantity", name="ck_commercial_grants_capacity"
        ),
        sa.CheckConstraint(
            "source IN ('plan', 'pack', 'manual', 'promotion')",
            name="ck_commercial_grants_source",
        ),
        sa.CheckConstraint(
            "resource IN ('ai_attendance', 'property_search_standard', "
            "'property_search_ai', 'image_optimization')",
            name="ck_commercial_grants_resource",
        ),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_commercial_grants_tenant_idempotency"
        ),
    )
    op.create_index(
        "ix_commercial_grants_tenant_resource",
        "commercial_entitlement_grants",
        ["tenant_id", "resource", "expires_at"],
    )
    op.create_table(
        "commercial_usage_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commercial_entitlement_grants.id", ondelete="SET NULL"),
        ),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("units", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.Text(), server_default="reserved", nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('reserved', 'settled', 'released')",
            name="ck_commercial_reservations_status",
        ),
        sa.CheckConstraint("units > 0", name="ck_commercial_reservations_units"),
        sa.CheckConstraint(
            "resource IN ('ai_attendance', 'property_search_standard', "
            "'property_search_ai', 'image_optimization')",
            name="ck_commercial_reservations_resource",
        ),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_commercial_reservations_tenant_idempotency"
        ),
    )
    op.create_index(
        "ix_commercial_reservations_status_expires",
        "commercial_usage_reservations",
        ["status", "expires_at"],
    )
    op.create_table(
        "commercial_usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commercial_entitlement_grants.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "reservation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commercial_usage_reservations.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("units", sa.Integer(), server_default="1", nullable=False),
        sa.Column("within_allowance", sa.Boolean(), nullable=False),
        sa.Column("mode_snapshot", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("units > 0", name="ck_commercial_events_units"),
        sa.CheckConstraint(
            "resource IN ('ai_attendance', 'property_search_standard', "
            "'property_search_ai', 'image_optimization')",
            name="ck_commercial_events_resource",
        ),
        sa.CheckConstraint(
            "mode_snapshot IN ('meter_only', 'enforce')", name="ck_commercial_events_mode"
        ),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_commercial_events_tenant_idempotency"
        ),
    )
    op.create_index(
        "ix_commercial_events_tenant_created",
        "commercial_usage_events",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_commercial_events_tenant_resource",
        "commercial_usage_events",
        ["tenant_id", "resource", "created_at"],
    )
    op.create_table(
        "ai_attendance_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_key", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("reservation_key", sa.Text(), nullable=False),
        sa.Column("opening_job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("response_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("delivered_job_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("close_reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'closed', 'released')",
            name="ck_ai_attendance_sessions_status",
        ),
        sa.CheckConstraint("response_count >= 0", name="ck_ai_attendance_sessions_responses"),
    )
    op.create_index(
        "ix_ai_attendance_sessions_tenant_expiry",
        "ai_attendance_sessions",
        ["tenant_id", "expires_at"],
    )
    op.create_index(
        "uq_ai_attendance_sessions_open_contact",
        "ai_attendance_sessions",
        ["tenant_id", "contact_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'active')"),
    )

    _seed_catalog()
    _backfill_pilot_subscriptions()


def _seed_catalog() -> None:
    plans = [
        (PILOT_PLAN_ID, "piloto_mvp", "Piloto MVP", 0, 300, 300, 30, 10, False),
        ("00000000-0000-4000-8000-000000000002", "operacao", "Operação", 19900, 0, 25, 0, 3, True),
        (
            "00000000-0000-4000-8000-000000000003",
            "ia_essencial",
            "IA Essencial",
            39900,
            100,
            100,
            10,
            5,
            True,
        ),
        (
            "00000000-0000-4000-8000-000000000004",
            "ia_profissional",
            "IA Profissional",
            69900,
            300,
            300,
            30,
            10,
            True,
        ),
        (
            "00000000-0000-4000-8000-000000000005",
            "ia_escala",
            "IA Escala",
            119900,
            700,
            800,
            80,
            20,
            True,
        ),
    ]
    for row in plans:
        op.execute(
            sa.text(
                """
                INSERT INTO commercial_plans
                    (id, code, name, version, monthly_price_cents, currency,
                     ai_attendances, property_searches, image_optimizations,
                     max_users, is_current, is_public, extra)
                VALUES
                    (CAST(:id AS uuid), :code, :name, 1, :price, 'BRL',
                     :ai, :searches, :images, :users, true, :public, '{}'::jsonb)
                """
            ).bindparams(
                id=row[0],
                code=row[1],
                name=row[2],
                price=row[3],
                ai=row[4],
                searches=row[5],
                images=row[6],
                users=row[7],
                public=row[8],
            )
        )
    packs = [
        (
            "00000000-0000-4000-8000-000000000101",
            "ai_100",
            "100 atendimentos de IA",
            "ai_attendance",
            100,
        ),
        (
            "00000000-0000-4000-8000-000000000102",
            "ai_300",
            "300 atendimentos de IA",
            "ai_attendance",
            300,
        ),
        (
            "00000000-0000-4000-8000-000000000103",
            "search_100",
            "100 buscas de imóveis",
            "property_search_standard",
            100,
        ),
        (
            "00000000-0000-4000-8000-000000000104",
            "images_20",
            "20 otimizações de fotos",
            "image_optimization",
            20,
        ),
    ]
    for row in packs:
        op.execute(
            sa.text(
                """
                INSERT INTO commercial_packs
                    (id, code, name, resource, units, currency, active, extra)
                VALUES
                    (CAST(:id AS uuid), :code, :name, :resource, :units, 'BRL', false,
                     '{"pricing_status":"pending_gateway"}'::jsonb)
                """
            ).bindparams(id=row[0], code=row[1], name=row[2], resource=row[3], units=row[4])
        )


def _backfill_pilot_subscriptions() -> None:
    op.execute(
        sa.text(
            f"""
            INSERT INTO tenant_commercial_subscriptions
                (tenant_id, plan_id, status, enforcement_mode, cycle_started_at, cycle_ends_at)
            SELECT id, CAST('{PILOT_PLAN_ID}' AS uuid), 'pilot', 'meter_only',
                   date_trunc('month', now()), date_trunc('month', now()) + interval '1 month'
            FROM tenants
            ON CONFLICT (tenant_id) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO commercial_entitlement_grants
                (id, tenant_id, resource, source, quantity, consumed_units, reserved_units,
                 idempotency_key, reference, valid_from, expires_at, extra)
            SELECT gen_random_uuid(), s.tenant_id, values.resource, 'plan', values.quantity,
                   0, 0,
                   'plan:' || s.plan_id::text || ':' || s.cycle_started_at::text
                       || ':' || values.resource,
                   'piloto_mvp', s.cycle_started_at, s.cycle_ends_at,
                   jsonb_build_object('plan_id', s.plan_id::text, 'cycle_start', s.cycle_started_at)
            FROM tenant_commercial_subscriptions s
            CROSS JOIN (VALUES
                ('ai_attendance', 300),
                ('property_search_standard', 300),
                ('image_optimization', 30)
            ) AS values(resource, quantity)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("uq_ai_attendance_sessions_open_contact", table_name="ai_attendance_sessions")
    op.drop_index("ix_ai_attendance_sessions_tenant_expiry", table_name="ai_attendance_sessions")
    op.drop_table("ai_attendance_sessions")
    op.drop_index("ix_commercial_events_tenant_resource", table_name="commercial_usage_events")
    op.drop_index("ix_commercial_events_tenant_created", table_name="commercial_usage_events")
    op.drop_table("commercial_usage_events")
    op.drop_index(
        "ix_commercial_reservations_status_expires",
        table_name="commercial_usage_reservations",
    )
    op.drop_table("commercial_usage_reservations")
    op.drop_index(
        "ix_commercial_grants_tenant_resource", table_name="commercial_entitlement_grants"
    )
    op.drop_table("commercial_entitlement_grants")
    op.drop_table("tenant_commercial_subscriptions")
    op.drop_table("commercial_packs")
    op.drop_table("commercial_plans")
