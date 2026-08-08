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
    INVITED = "invited"


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
    session_version: int = 0
    is_master: bool = False
    must_change_password: bool = False
    invitation_expires_at: datetime | None = None
    invited_at: datetime | None = None
    last_login_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class UserAuditLog:
    tenant_id: UUID
    action: str
    changes: dict[str, object]
    actor_user_id: UUID | None = None
    target_user_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
