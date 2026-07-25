from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MaintenanceTicketCreated:
    tenant_id: UUID
    ticket_id: UUID
    conversation_id: UUID | None
