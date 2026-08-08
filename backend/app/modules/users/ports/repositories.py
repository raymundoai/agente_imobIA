from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.users.domain.entities import User, UserAuditLog, UserRole, UserStatus


class UserRepositoryPort(ABC):
    @abstractmethod
    def add(self, tenant_id: UUID, user: User) -> User: ...

    @abstractmethod
    def get_by_id(self, tenant_id: UUID, user_id: UUID) -> User | None: ...

    @abstractmethod
    def get_by_email(self, tenant_id: UUID, email: str) -> User | None: ...

    @abstractmethod
    def get_by_invitation_hash(self, token_hash: str) -> User | None: ...

    @abstractmethod
    def list(self, tenant_id: UUID) -> list[User]: ...

    @abstractmethod
    def count_active_admins_for_update(self, tenant_id: UUID) -> int: ...

    @abstractmethod
    def update(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        name: str | None,
        email: str | None,
        role: UserRole | None,
        status: UserStatus | None,
        revoke_sessions: bool = False,
    ) -> User | None: ...

    @abstractmethod
    def set_invitation(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        token_hash: str,
        expires_at: datetime,
        invited: bool,
    ) -> User | None: ...

    @abstractmethod
    def accept_invitation(self, user_id: UUID, *, hashed_password: str) -> User | None: ...

    @abstractmethod
    def revoke_sessions(self, tenant_id: UUID, user_id: UUID) -> User | None: ...

    @abstractmethod
    def delete(self, tenant_id: UUID, user_id: UUID) -> bool: ...

    @abstractmethod
    def change_password(
        self, tenant_id: UUID, user_id: UUID, *, hashed_password: str
    ) -> User | None: ...

    @abstractmethod
    def record_login(self, tenant_id: UUID, user_id: UUID) -> User | None: ...

    @abstractmethod
    def add_audit(self, audit: UserAuditLog) -> UserAuditLog: ...

    @abstractmethod
    def list_audit(self, tenant_id: UUID, limit: int = 100) -> list[UserAuditLog]: ...
