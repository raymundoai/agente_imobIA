from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.maintenance.adapters.repositories import SqlAlchemyMaintenanceTicketRepository
from app.modules.maintenance.application.use_cases import (
    GetMaintenanceTicketUseCase,
    ListMaintenanceTicketsUseCase,
    MaintenanceTicketingService,
    UpdateMaintenanceTicketStatusUseCase,
)
from app.modules.maintenance.domain.entities import MaintenanceTicket, MaintenanceTicketStatus
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class CreateMaintenanceTicketRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=3, max_length=40)
    property_reference: str | None = None
    issue_type: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    urgency: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class UpdateMaintenanceTicketStatusRequest(BaseModel):
    status: MaintenanceTicketStatus


class MaintenanceTicketResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID | None
    customer_name: str
    phone: str
    property_reference: str | None
    issue_type: str
    description: str
    urgency: str
    status: str
    assigned_user_id: UUID | None
    attachments: list[dict[str, Any]]

    @classmethod
    def from_domain(cls, ticket: MaintenanceTicket) -> "MaintenanceTicketResponse":
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
        )


@router.post(
    "/tickets", response_model=MaintenanceTicketResponse, status_code=status.HTTP_201_CREATED
)
def create_ticket(
    payload: CreateMaintenanceTicketRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> MaintenanceTicketResponse:
    ticket = MaintenanceTicketingService(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyMaintenanceTicketRepository(session),
        container.event_bus,
    ).create_ticket(principal.tenant_id, payload.model_dump())
    return MaintenanceTicketResponse.from_domain(ticket)


@router.get("/tickets", response_model=list[MaintenanceTicketResponse])
def list_tickets(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[MaintenanceTicketResponse]:
    tickets = ListMaintenanceTicketsUseCase(SqlAlchemyMaintenanceTicketRepository(session)).execute(
        principal.tenant_id, limit=limit, offset=offset
    )
    return [MaintenanceTicketResponse.from_domain(ticket) for ticket in tickets]


@router.get("/tickets/{ticket_id}", response_model=MaintenanceTicketResponse)
def get_ticket(
    ticket_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> MaintenanceTicketResponse:
    ticket = GetMaintenanceTicketUseCase(SqlAlchemyMaintenanceTicketRepository(session)).execute(
        principal.tenant_id, ticket_id
    )
    return MaintenanceTicketResponse.from_domain(ticket)


@router.patch("/tickets/{ticket_id}", response_model=MaintenanceTicketResponse)
def update_ticket_status(
    ticket_id: UUID,
    payload: UpdateMaintenanceTicketStatusRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> MaintenanceTicketResponse:
    ticket = UpdateMaintenanceTicketStatusUseCase(
        SqlAlchemyMaintenanceTicketRepository(session)
    ).execute(principal.tenant_id, ticket_id, payload.status)
    return MaintenanceTicketResponse.from_domain(ticket)
