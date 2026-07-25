from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class UsageType(StrEnum):
    MESSAGE = "message"


@dataclass(slots=True)
class UsageRecord:
    tenant_id: UUID
    type: UsageType
    module: str
    id: UUID = field(default_factory=uuid4)
    quantity: int = 1
    related_entity_id: UUID | None = None
    estimated_cost: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
