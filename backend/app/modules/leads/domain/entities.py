from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class LeadPurpose(StrEnum):
    BUY = "buy"
    RENT = "rent"


class LeadDemandStatus(StrEnum):
    OPEN = "open"
    QUALIFIED = "qualified"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


@dataclass(slots=True)
class LeadDemand:
    tenant_id: UUID
    lead_name: str
    phone: str
    id: UUID = field(default_factory=uuid4)
    contact_id: UUID | None = None
    conversation_id: UUID | None = None
    purpose: LeadPurpose | None = None
    property_type: str | None = None
    city: str | None = None
    neighborhoods: list[str] = field(default_factory=list)
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    bedrooms: int | None = None
    parking_spaces: int | None = None
    min_area: int | None = None
    notes: str | None = None
    status: LeadDemandStatus = LeadDemandStatus.OPEN
    responsible_user_id: UUID | None = None
    crm_contact_id: str | None = None
    crm_deal_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
