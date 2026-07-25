from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from app.modules.leads.domain.entities import LeadDemand


class LeadQualificationPort(ABC):
    @abstractmethod
    def create_or_update_lead(
        self,
        tenant_id: UUID,
        data: dict[str, Any],
        *,
        conversation_id: UUID | None = None,
        handoff_reason: str | None = None,
    ) -> LeadDemand:
        raise NotImplementedError
