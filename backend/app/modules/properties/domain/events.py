from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PropertyCaptured:
    tenant_id: UUID
    property_id: UUID
    demand_id: UUID | None


@dataclass(frozen=True, slots=True)
class PropertyDemandCreated:
    tenant_id: UUID
    demand_id: UUID
