from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class MaintenanceUrgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MaintenanceTicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


@dataclass(slots=True)
class MaintenanceTicket:
    tenant_id: UUID
    customer_name: str
    phone: str
    issue_type: str
    description: str
    id: UUID = field(default_factory=uuid4)
    conversation_id: UUID | None = None
    property_reference: str | None = None
    urgency: MaintenanceUrgency = MaintenanceUrgency.MEDIUM
    status: MaintenanceTicketStatus = MaintenanceTicketStatus.OPEN
    assigned_user_id: UUID | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
