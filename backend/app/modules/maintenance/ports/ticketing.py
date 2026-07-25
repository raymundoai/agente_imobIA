from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from app.modules.maintenance.domain.entities import MaintenanceTicket


class MaintenanceTicketingPort(ABC):
    @abstractmethod
    def create_ticket(
        self,
        tenant_id: UUID,
        data: dict[str, Any],
        *,
        conversation_id: UUID | None = None,
    ) -> MaintenanceTicket:
        raise NotImplementedError
