from uuid import UUID

from app.modules.auth.ports.security import PasswordHasherPort
from app.modules.users.domain.entities import User, UserRole, UserStatus
from app.modules.users.ports.repositories import UserRepositoryPort
from app.shared.errors.exceptions import NotFoundError
from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort


class CreateUserUseCase:
    def __init__(
        self,
        users: UserRepositoryPort,
        passwords: PasswordHasherPort,
        events: EventBusPort,
    ) -> None:
        self._users = users
        self._passwords = passwords
        self._events = events

    def execute(
        self,
        tenant_id: UUID,
        name: str,
        email: str,
        password: str,
        role: UserRole,
    ) -> User:
        user = User(
            tenant_id=tenant_id,
            name=name.strip(),
            email=email.strip().lower(),
            hashed_password=self._passwords.hash(password),
            role=role,
        )
        created = self._users.add(tenant_id, user)
        self._events.publish(
            DomainEvent(
                name="UserCreated",
                tenant_id=tenant_id,
                payload={"user_id": str(created.id), "role": created.role.value},
            )
        )
        return created


class ListUsersUseCase:
    def __init__(self, users: UserRepositoryPort) -> None:
        self._users = users

    def execute(self, tenant_id: UUID) -> list[User]:
        return self._users.list(tenant_id)


class UpdateUserUseCase:
    def __init__(self, users: UserRepositoryPort) -> None:
        self._users = users

    def execute(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        name: str | None,
        role: UserRole | None,
        status: UserStatus | None,
    ) -> User:
        user = self._users.update(tenant_id, user_id, name=name, role=role, status=status)
        if user is None:
            raise NotFoundError("User not found")
        return user
