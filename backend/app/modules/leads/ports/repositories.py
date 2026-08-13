from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.leads.domain.entities import LeadDemand


class LeadDemandRepositoryPort(ABC):
    @abstractmethod
    def lock_phone(self, tenant_id: UUID, phone: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def create(self, tenant_id: UUID, lead: LeadDemand) -> LeadDemand:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, tenant_id: UUID, lead_id: UUID) -> LeadDemand | None:
        raise NotImplementedError

    @abstractmethod
    def get_open_by_phone(self, tenant_id: UUID, phone: str) -> LeadDemand | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, tenant_id: UUID, lead: LeadDemand) -> LeadDemand:
        raise NotImplementedError

    @abstractmethod
    def delete(self, tenant_id: UUID, lead_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(
        self,
        tenant_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        contact_id: UUID | None = None,
    ) -> list[LeadDemand]:
        raise NotImplementedError
