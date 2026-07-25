from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.maintenance.domain.entities import (
    MaintenanceTicket,
    MaintenanceTicketStatus,
)


class MaintenanceTicketRepositoryPort(ABC):
    @abstractmethod
    def create(self, tenant_id: UUID, ticket: MaintenanceTicket) -> MaintenanceTicket:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, tenant_id: UUID, ticket_id: UUID) -> MaintenanceTicket | None:
        raise NotImplementedError

    @abstractmethod
    def list(self, tenant_id: UUID, *, limit: int = 50, offset: int = 0) -> list[MaintenanceTicket]:
        raise NotImplementedError

    @abstractmethod
    def update_status(
        self, tenant_id: UUID, ticket_id: UUID, status: MaintenanceTicketStatus
    ) -> MaintenanceTicket | None:
        raise NotImplementedError
