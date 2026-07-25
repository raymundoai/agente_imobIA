from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ContactReference:
    id: UUID
    phone: str


class ContactUpsertPort(Protocol):
    def upsert(
        self,
        tenant_id: UUID,
        *,
        phone: str,
        name: str | None,
        email: str | None = None,
        interest: str | None = None,
        notes: str | None = None,
        source: str | None = None,
    ) -> ContactReference: ...
