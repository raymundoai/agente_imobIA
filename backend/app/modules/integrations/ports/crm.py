from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class CrmCredentials:
    base_url: str
    access_token: str
    pipeline_id: str | None = None
    stage_ids: dict[str, str] = field(default_factory=dict)
    owner_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CrmContact:
    id: str
    properties: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CrmDeal:
    id: str
    properties: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CreateOrUpdateContactData:
    name: str
    phone: str
    email: str | None = None


@dataclass(frozen=True, slots=True)
class CreateDealData:
    name: str
    stage: str
    pipeline: str | None
    amount: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CreateNoteData:
    body: str
    timestamp: datetime
    owner_id: str | None = None


@dataclass(frozen=True, slots=True)
class CreateTaskData:
    subject: str
    body: str
    timestamp: datetime
    owner_id: str | None = None
    priority: str = "HIGH"


class CrmPort(ABC):
    @abstractmethod
    def search_contact_by_phone(self, credentials: CrmCredentials, phone: str) -> CrmContact | None:
        raise NotImplementedError

    @abstractmethod
    def create_contact(
        self, credentials: CrmCredentials, data: CreateOrUpdateContactData
    ) -> CrmContact:
        raise NotImplementedError

    @abstractmethod
    def update_contact(
        self, credentials: CrmCredentials, contact_id: str, data: CreateOrUpdateContactData
    ) -> CrmContact:
        raise NotImplementedError

    @abstractmethod
    def create_deal(self, credentials: CrmCredentials, data: CreateDealData) -> CrmDeal:
        raise NotImplementedError

    @abstractmethod
    def associate(
        self,
        credentials: CrmCredentials,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_note(
        self,
        credentials: CrmCredentials,
        data: CreateNoteData,
        associations: list[tuple[str, str]],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def create_task(
        self,
        credentials: CrmCredentials,
        data: CreateTaskData,
        associations: list[tuple[str, str]],
    ) -> str:
        raise NotImplementedError


class CrmCredentialsPort(ABC):
    @abstractmethod
    def get(self, tenant_slug: str) -> CrmCredentials | None:
        raise NotImplementedError
