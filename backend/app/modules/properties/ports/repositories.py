from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from app.modules.leads.domain.entities import LeadDemand
from app.modules.properties.domain.entities import Property


class PropertyRepositoryPort(ABC):
    @abstractmethod
    def create_manual(self, tenant_id: UUID, property: Property) -> Property:
        raise NotImplementedError

    @abstractmethod
    def upsert_captured(
        self, tenant_id: UUID, property: Property, demand_id: UUID | None
    ) -> Property:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, tenant_id: UUID, property_id: UUID) -> Property | None:
        raise NotImplementedError

    @abstractmethod
    def list(
        self, tenant_id: UUID, *, demand_id: UUID | None = None, limit: int = 50, offset: int = 0
    ) -> list[Property]:
        raise NotImplementedError

    @abstractmethod
    def search_matching(
        self, tenant_id: UUID, demand: LeadDemand, limit: int = 50
    ) -> list[Property]:
        raise NotImplementedError

    @abstractmethod
    def search_by_filters(
        self,
        tenant_id: UUID,
        *,
        city: str | None = None,
        purpose: str | None = None,
        property_type: str | None = None,
        neighborhoods: list[str] | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        bedrooms: int | None = None,
        parking_spaces: int | None = None,
        limit: int = 5,
    ) -> list[Property]:
        raise NotImplementedError
