from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.leads.domain.entities import LeadDemand
from app.shared.database.base import Base


class LeadDemandModel(Base):
    __tablename__ = "lead_demands"
    __table_args__ = (
        CheckConstraint("purpose IN ('buy', 'rent') OR purpose IS NULL", name="purpose"),
        CheckConstraint(
            "status IN ('open', 'qualified', 'in_progress', 'closed')",
            name="status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "responsible_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_lead_demands_tenant_responsible_user",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_lead_demands_tenant_id_id"),
        Index("ix_lead_demands_tenant_status", "tenant_id", "status"),
        Index("ix_lead_demands_tenant_phone", "tenant_id", "phone"),
        Index(
            "ix_lead_demands_tenant_created",
            "tenant_id",
            text("created_at DESC"),
        ),
        Index(
            "uq_lead_demands_open_phone",
            "tenant_id",
            "phone",
            unique=True,
            postgresql_where=text("status <> 'closed'"),
        ),
        Index(
            "ix_lead_demands_tenant_crm_contact",
            "tenant_id",
            "crm_contact_id",
            postgresql_where=text("crm_contact_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_lead_demands_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    property_type: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    neighborhoods: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'::text[]")
    )
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    parking_spaces: Mapped[int | None] = mapped_column(Integer)
    min_area: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default="open")
    responsible_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    crm_contact_id: Mapped[str | None] = mapped_column(Text)
    crm_deal_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @classmethod
    def from_domain(cls, lead: LeadDemand) -> "LeadDemandModel":
        return cls(
            id=lead.id,
            tenant_id=lead.tenant_id,
            lead_name=lead.lead_name,
            phone=lead.phone,
            purpose=lead.purpose.value if lead.purpose else None,
            property_type=lead.property_type,
            city=lead.city,
            neighborhoods=lead.neighborhoods,
            price_min=lead.price_min,
            price_max=lead.price_max,
            bedrooms=lead.bedrooms,
            parking_spaces=lead.parking_spaces,
            min_area=lead.min_area,
            notes=lead.notes,
            status=lead.status.value,
            responsible_user_id=lead.responsible_user_id,
            crm_contact_id=lead.crm_contact_id,
            crm_deal_id=lead.crm_deal_id,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )
