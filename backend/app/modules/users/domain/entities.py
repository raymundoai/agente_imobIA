from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class UserRole(StrEnum):
    ADMIN = "admin"
    GESTOR = "gestor"
    CORRETOR = "corretor"
    ATENDENTE = "atendente"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(slots=True)
class User:
    tenant_id: UUID
    name: str
    email: str
    hashed_password: str
    role: UserRole
    id: UUID = field(default_factory=uuid4)
    status: UserStatus = UserStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
