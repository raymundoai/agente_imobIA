from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class LeadQualified:
    tenant_id: UUID
    lead_demand_id: UUID
    crm_contact_id: str | None
    crm_deal_id: str | None
