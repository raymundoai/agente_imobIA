from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class UsageRecordModel(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_usage_records_tenant_id", "tenant_id"),
        Index("ix_usage_records_tenant_type_created", "tenant_id", "type", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_usage_records_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    module: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreditAccountModel(Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint(
            "enforcement_mode IN ('meter_only', 'enforce')",
            name="credit_accounts_enforcement_mode",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_credit_accounts_tenant_id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance_credits: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    reserved_credits: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    enforcement_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="meter_only", server_default="meter_only"
    )
    unlimited_messages: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CreditLedgerModel(Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_credit_ledger_tenant_idempotency"
        ),
        Index("ix_credit_ledger_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_credit_ledger_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    delta_credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    provider_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 8), nullable=False, default=Decimal("0"), server_default="0"
    )
    retail_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 8), nullable=False, default=Decimal("0"), server_default="0"
    )
    reference_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreditReservationModel(Base):
    __tablename__ = "credit_reservations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_credit_reservations_tenant_idempotency",
        ),
        CheckConstraint(
            "status IN ('reserved', 'started', 'settled', 'released')",
            name="credit_reservations_status",
        ),
        Index("ix_credit_reservations_status_expires", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="reserved")
    reserved_credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_credits: Mapped[int | None] = mapped_column(BigInteger)
    reference_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommercialPlanModel(Base):
    __tablename__ = "commercial_plans"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_commercial_plans_code_version"),
        Index(
            "uq_commercial_plans_current_code",
            "code",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        CheckConstraint("monthly_price_cents >= 0", name="price"),
        CheckConstraint("max_users > 0", name="max_users"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    monthly_price_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="BRL", server_default="BRL")
    ai_attendances: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    property_searches: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    image_optimizations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_users: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CommercialPackModel(Base):
    __tablename__ = "commercial_packs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_commercial_packs_code"),
        CheckConstraint("units > 0", name="units"),
        CheckConstraint(
            "resource IN ('ai_attendance', 'property_search_standard', "
            "'property_search_ai', 'image_optimization')",
            name="resource",
        ),
        CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="price"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    price_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="BRL", server_default="BRL")
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TenantCommercialSubscriptionModel(Base):
    __tablename__ = "tenant_commercial_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pilot', 'active', 'past_due', 'cancelled')",
            name="status",
        ),
        CheckConstraint(
            "enforcement_mode IN ('meter_only', 'enforce')",
            name="enforcement",
        ),
        CheckConstraint(
            "cycle_ends_at > cycle_started_at",
            name="cycle",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("commercial_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pilot", server_default="pilot"
    )
    enforcement_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="meter_only", server_default="meter_only"
    )
    cycle_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cycle_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CommercialEntitlementGrantModel(Base):
    __tablename__ = "commercial_entitlement_grants"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_commercial_grants_tenant_idempotency"
        ),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("consumed_units >= 0", name="consumed"),
        CheckConstraint("reserved_units >= 0", name="reserved"),
        CheckConstraint(
            "consumed_units + reserved_units <= quantity",
            name="capacity",
        ),
        CheckConstraint(
            "source IN ('plan', 'pack', 'manual', 'promotion')",
            name="source",
        ),
        CheckConstraint(
            "resource IN ('ai_attendance', 'property_search_standard', "
            "'property_search_ai', 'image_optimization')",
            name="resource",
        ),
        Index("ix_commercial_grants_tenant_resource", "tenant_id", "resource", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_units: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    reserved_units: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CommercialUsageReservationModel(Base):
    __tablename__ = "commercial_usage_reservations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_commercial_reservations_tenant_idempotency"
        ),
        CheckConstraint(
            "status IN ('reserved', 'settled', 'released')",
            name="status",
        ),
        CheckConstraint("units > 0", name="units"),
        CheckConstraint(
            "resource IN ('ai_attendance', 'property_search_standard', "
            "'property_search_ai', 'image_optimization')",
            name="resource",
        ),
        Index("ix_commercial_reservations_status_expires", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    grant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("commercial_entitlement_grants.id", ondelete="SET NULL")
    )
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="reserved", server_default="reserved"
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommercialUsageEventModel(Base):
    __tablename__ = "commercial_usage_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_commercial_events_tenant_idempotency"
        ),
        CheckConstraint("units > 0", name="units"),
        CheckConstraint(
            "resource IN ('ai_attendance', 'property_search_standard', "
            "'property_search_ai', 'image_optimization')",
            name="resource",
        ),
        CheckConstraint("mode_snapshot IN ('meter_only', 'enforce')", name="mode"),
        Index("ix_commercial_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_commercial_events_tenant_resource", "tenant_id", "resource", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    grant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("commercial_entitlement_grants.id", ondelete="SET NULL")
    )
    reservation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("commercial_usage_reservations.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    within_allowance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mode_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AiAttendanceSessionModel(Base):
    __tablename__ = "ai_attendance_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'closed', 'released')",
            name="status",
        ),
        CheckConstraint("response_count >= 0", name="responses"),
        Index("ix_ai_attendance_sessions_tenant_expiry", "tenant_id", "expires_at"),
        Index(
            "uq_ai_attendance_sessions_open_contact",
            "tenant_id",
            "contact_key",
            unique=True,
            postgresql_where=text("status IN ('pending', 'active')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    contact_key: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    reservation_key: Mapped[str] = mapped_column(Text, nullable=False)
    opening_job_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    response_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    delivered_job_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
