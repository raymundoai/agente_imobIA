from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.users.domain.entities import User, UserRole, UserStatus


class UserRepositoryPort(ABC):
    @abstractmethod
    def add(self, tenant_id: UUID, user: User) -> User: ...

    @abstractmethod
    def get_by_id(self, tenant_id: UUID, user_id: UUID) -> User | None: ...

    @abstractmethod
    def get_by_email(self, tenant_id: UUID, email: str) -> User | None: ...

    @abstractmethod
    def list(self, tenant_id: UUID) -> list[User]: ...

    @abstractmethod
    def update(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        name: str | None,
        role: UserRole | None,
        status: UserStatus | None,
    ) -> User | None: ...
