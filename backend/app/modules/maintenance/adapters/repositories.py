from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.maintenance.adapters.models import MaintenanceTicketModel
from app.modules.maintenance.domain.entities import (
    MaintenanceTicket,
    MaintenanceTicketStatus,
    MaintenanceUrgency,
)
from app.modules.maintenance.ports.repositories import MaintenanceTicketRepositoryPort


def _to_domain(model: MaintenanceTicketModel) -> MaintenanceTicket:
    return MaintenanceTicket(
        id=model.id,
        tenant_id=model.tenant_id,
        conversation_id=model.conversation_id,
        customer_name=model.customer_name,
        phone=model.phone,
        property_reference=model.property_reference,
        issue_type=model.issue_type,
        description=model.description,
        urgency=MaintenanceUrgency(model.urgency),
        status=MaintenanceTicketStatus(model.status),
        assigned_user_id=model.assigned_user_id,
        attachments=model.attachments,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyMaintenanceTicketRepository(MaintenanceTicketRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, tenant_id: UUID, ticket: MaintenanceTicket) -> MaintenanceTicket:
        if ticket.tenant_id != tenant_id:
            raise ValueError("Ticket tenant does not match repository scope")
        model = MaintenanceTicketModel.from_domain(ticket)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def get_by_id(self, tenant_id: UUID, ticket_id: UUID) -> MaintenanceTicket | None:
        model = self._session.scalar(
            select(MaintenanceTicketModel).where(
                MaintenanceTicketModel.tenant_id == tenant_id,
                MaintenanceTicketModel.id == ticket_id,
            )
        )
        return _to_domain(model) if model else None

    def list(self, tenant_id: UUID, *, limit: int = 50, offset: int = 0) -> list[MaintenanceTicket]:
        models = self._session.scalars(
            select(MaintenanceTicketModel)
            .where(MaintenanceTicketModel.tenant_id == tenant_id)
            .order_by(MaintenanceTicketModel.created_at.desc(), MaintenanceTicketModel.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_domain(model) for model in models]

    def update_status(
        self, tenant_id: UUID, ticket_id: UUID, status: MaintenanceTicketStatus
    ) -> MaintenanceTicket | None:
        model = self._session.scalar(
            select(MaintenanceTicketModel).where(
                MaintenanceTicketModel.tenant_id == tenant_id,
                MaintenanceTicketModel.id == ticket_id,
            )
        )
        if model is None:
            return None
        model.status = status.value
        model.updated_at = datetime.now(UTC)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)
