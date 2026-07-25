from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.maintenance.domain.entities import MaintenanceTicket
from app.shared.database.base import Base


class MaintenanceTicketModel(Base):
    __tablename__ = "maintenance_tickets"
    __table_args__ = (
        CheckConstraint(
            "urgency IN ('low', 'medium', 'high', 'critical')",
            name="urgency",
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved')",
            name="status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_maintenance_tickets_tenant_conversation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_maintenance_tickets_tenant_assigned_user",
        ),
        Index("ix_maintenance_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_maintenance_tickets_tenant_urgency", "tenant_id", "urgency"),
        Index(
            "ix_maintenance_tickets_tenant_created",
            "tenant_id",
            sql_text("created_at DESC"),
        ),
        Index(
            "ix_maintenance_tickets_tenant_conversation",
            "tenant_id",
            "conversation_id",
            postgresql_where=sql_text("conversation_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_maintenance_tickets_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    property_reference: Mapped[str | None] = mapped_column(Text)
    issue_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[str] = mapped_column(
        Text, nullable=False, default="medium", server_default="medium"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default="open")
    assigned_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @classmethod
    def from_domain(cls, ticket: MaintenanceTicket) -> "MaintenanceTicketModel":
        return cls(
            id=ticket.id,
            tenant_id=ticket.tenant_id,
            conversation_id=ticket.conversation_id,
            customer_name=ticket.customer_name,
            phone=ticket.phone,
            property_reference=ticket.property_reference,
            issue_type=ticket.issue_type,
            description=ticket.description,
            urgency=ticket.urgency.value,
            status=ticket.status.value,
            assigned_user_id=ticket.assigned_user_id,
            attachments=ticket.attachments,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )
