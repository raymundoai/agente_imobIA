from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.modules.maintenance.domain.entities import (
    MaintenanceTicket,
    MaintenanceTicketStatus,
    MaintenanceUrgency,
)
from app.modules.maintenance.ports.repositories import MaintenanceTicketRepositoryPort
from app.modules.maintenance.ports.ticketing import MaintenanceTicketingPort
from app.modules.tenants.domain.entities import TenantStatus
from app.modules.tenants.ports.repositories import TenantRepositoryPort
from app.shared.errors.exceptions import NotFoundError
from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort


class MaintenanceTicketingService(MaintenanceTicketingPort):
    def __init__(
        self,
        tenants: TenantRepositoryPort,
        tickets: MaintenanceTicketRepositoryPort,
        events: EventBusPort,
    ) -> None:
        self._tenants = tenants
        self._tickets = tickets
        self._events = events

    def create_ticket(
        self,
        tenant_id: UUID,
        data: dict[str, Any],
        *,
        conversation_id: UUID | None = None,
    ) -> MaintenanceTicket:
        tenant = self._tenants.get_by_id(tenant_id)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            raise NotFoundError("Tenant not found")
        ticket = MaintenanceTicket(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            customer_name=_text(data.get("customer_name")) or "Cliente",
            phone=_text(data.get("phone")),
            property_reference=_optional_text(data.get("property_reference")),
            issue_type=_text(data.get("issue_type")) or "maintenance",
            description=_text(data.get("description")) or "Solicitação de manutenção",
            urgency=_urgency(data.get("urgency"), data.get("description")),
            attachments=data.get("attachments")
            if isinstance(data.get("attachments"), list)
            else [],
        )
        saved = self._tickets.create(tenant_id, ticket)
        self._events.publish(
            DomainEvent(
                name="MaintenanceTicketCreated",
                tenant_id=tenant_id,
                payload={
                    "ticket_id": str(saved.id),
                    "conversation_id": str(conversation_id) if conversation_id else None,
                    "urgency": saved.urgency.value,
                },
            )
        )
        if saved.urgency in {MaintenanceUrgency.HIGH, MaintenanceUrgency.CRITICAL}:
            self._events.publish(
                DomainEvent(
                    name="HumanHandoffRequested",
                    tenant_id=tenant_id,
                    payload={
                        "conversation_id": str(conversation_id) if conversation_id else None,
                        "reason": f"maintenance_{saved.urgency.value}",
                    },
                )
            )
        return saved


class ListMaintenanceTicketsUseCase:
    def __init__(self, tickets: MaintenanceTicketRepositoryPort) -> None:
        self._tickets = tickets

    def execute(
        self, tenant_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[MaintenanceTicket]:
        return self._tickets.list(tenant_id, limit=limit, offset=offset)


class GetMaintenanceTicketUseCase:
    def __init__(self, tickets: MaintenanceTicketRepositoryPort) -> None:
        self._tickets = tickets

    def execute(self, tenant_id: UUID, ticket_id: UUID) -> MaintenanceTicket:
        ticket = self._tickets.get_by_id(tenant_id, ticket_id)
        if ticket is None:
            raise NotFoundError("Maintenance ticket not found")
        return ticket


class UpdateMaintenanceTicketStatusUseCase:
    def __init__(self, tickets: MaintenanceTicketRepositoryPort) -> None:
        self._tickets = tickets

    def execute(
        self, tenant_id: UUID, ticket_id: UUID, status: MaintenanceTicketStatus
    ) -> MaintenanceTicket:
        ticket = self._tickets.update_status(tenant_id, ticket_id, status)
        if ticket is None:
            raise NotFoundError("Maintenance ticket not found")
        return ticket


def detect_restricted_intent(text: str) -> str | None:
    normalized = text.lower()
    groups = {
        "financial_negotiation": [
            "desconto",
            "parcelamento",
            "negociar valor",
            "abaixar aluguel",
            "inadimplência",
            "inadimplencia",
        ],
        "legal_or_contract": [
            "jurídico",
            "juridico",
            "processar",
            "rescisão",
            "rescisao",
            "cancelar contrato",
            "alterar contrato",
            "quebrar contrato",
        ],
    }
    for reason, terms in groups.items():
        if any(term in normalized for term in terms):
            return reason
    return None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _urgency(value: Any, description: Any) -> MaintenanceUrgency:
    if value:
        try:
            return MaintenanceUrgency(str(value))
        except ValueError:
            pass
    normalized = _text(description).lower()
    if any(term in normalized for term in ["vazamento de gás", "gas", "incêndio", "fogo"]):
        return MaintenanceUrgency.CRITICAL
    if any(term in normalized for term in ["vazamento", "sem energia", "alagamento"]):
        return MaintenanceUrgency.HIGH
    return MaintenanceUrgency.MEDIUM


def touch_now() -> datetime:
    return datetime.now(UTC)
