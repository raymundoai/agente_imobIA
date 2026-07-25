from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
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
