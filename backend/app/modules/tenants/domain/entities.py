from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class TenantStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(slots=True)
class Tenant:
    name: str
    slug: str
    id: UUID = field(default_factory=uuid4)
    status: TenantStatus = TenantStatus.ACTIVE
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
