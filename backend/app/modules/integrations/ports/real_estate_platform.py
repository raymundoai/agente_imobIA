from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PlatformCredentials:
    base_url: str
    access_token: str


@dataclass(frozen=True, slots=True)
class PlatformPage:
    items: list[dict[str, Any]]
    page: int
    per_page: int
    total: int | None = None


@dataclass(frozen=True, slots=True)
class PlatformContactData:
    name: str
    phone: str | None = None
    email: str | None = None
    owner_user_id: str | None = None
    group_ids: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class PlatformLeadData:
    name: str
    phone: str | None = None
    email: str | None = None
    property_ids: list[str] = field(default_factory=list)
    owner_user_id: str | None = None
    note: str | None = None


class RealEstatePlatformPort(ABC):
    @abstractmethod
    def list_properties(
        self,
        credentials: PlatformCredentials,
        *,
        page: int = 1,
        per_page: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> PlatformPage:
        raise NotImplementedError

    @abstractmethod
    def get_property(self, credentials: PlatformCredentials, property_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_contacts(
        self,
        credentials: PlatformCredentials,
        *,
        page: int = 1,
        per_page: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> PlatformPage:
        raise NotImplementedError

    @abstractmethod
    def create_contact(
        self, credentials: PlatformCredentials, data: PlatformContactData
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_lead(
        self, credentials: PlatformCredentials, data: PlatformLeadData
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_users(
        self, credentials: PlatformCredentials, *, page: int = 1, per_page: int = 20
    ) -> PlatformPage:
        raise NotImplementedError

    @abstractmethod
    def list_contact_groups(self, credentials: PlatformCredentials) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def add_note(
        self,
        credentials: PlatformCredentials,
        *,
        user_id: str,
        note: str,
        contact_id: str | None = None,
        property_id: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError
