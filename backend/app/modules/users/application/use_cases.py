from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.modules.auth.ports.security import PasswordHasherPort
from app.modules.users.domain.entities import (
    User,
    UserAuditLog,
    UserRole,
    UserStatus,
)
from app.modules.users.ports.repositories import UserRepositoryPort
from app.shared.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort


@dataclass(frozen=True, slots=True)
class PasswordSetup:
    user: User
    token: str
    expires_at: datetime


def invitation_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
        *,
        actor_user_id: UUID | None = None,
    ) -> User:
        user = User(
            tenant_id=tenant_id,
            name=name.strip(),
            email=email.strip().lower(),
            hashed_password=self._passwords.hash(password),
            role=role,
        )
        created = self._users.add(tenant_id, user)
        self._audit(
            tenant_id,
            actor_user_id,
            created.id,
            "user_created",
            {"role": created.role.value, "status": created.status.value},
        )
        self._events.publish(
            DomainEvent(
                name="UserCreated",
                tenant_id=tenant_id,
                payload={"user_id": str(created.id), "role": created.role.value},
            )
        )
        return created

    def _audit(
        self,
        tenant_id: UUID,
        actor_user_id: UUID | None,
        target_user_id: UUID,
        action: str,
        changes: dict[str, object],
    ) -> None:
        self._users.add_audit(
            UserAuditLog(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                action=action,
                changes=changes,
            )
        )


class InviteUserUseCase:
    def __init__(
        self,
        users: UserRepositoryPort,
        passwords: PasswordHasherPort,
        events: EventBusPort,
        *,
        ttl_hours: int = 168,
    ) -> None:
        self._users = users
        self._passwords = passwords
        self._events = events
        self._ttl = timedelta(hours=ttl_hours)

    def execute(
        self,
        tenant_id: UUID,
        actor_user_id: UUID,
        name: str,
        email: str,
        role: UserRole,
    ) -> PasswordSetup:
        placeholder = secrets.token_urlsafe(48)
        user = User(
            tenant_id=tenant_id,
            name=name.strip(),
            email=email.strip().lower(),
            hashed_password=self._passwords.hash(placeholder),
            role=role,
            status=UserStatus.INVITED,
            must_change_password=True,
        )
        created = self._users.add(tenant_id, user)
        setup = self._set_token(tenant_id, created, invited=True)
        self._users.add_audit(
            UserAuditLog(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                target_user_id=created.id,
                action="user_invited",
                changes={"role": role.value, "email": created.email},
            )
        )
        self._events.publish(
            DomainEvent(
                name="UserInvited",
                tenant_id=tenant_id,
                payload={"user_id": str(created.id), "role": role.value},
            )
        )
        return setup

    def _set_token(self, tenant_id: UUID, user: User, *, invited: bool) -> PasswordSetup:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + self._ttl
        updated = self._users.set_invitation(
            tenant_id,
            user.id,
            token_hash=invitation_token_hash(token),
            expires_at=expires_at,
            invited=invited,
        )
        if updated is None:
            raise NotFoundError("User not found")
        return PasswordSetup(updated, token, expires_at)


class GeneratePasswordSetupUseCase:
    def __init__(
        self,
        users: UserRepositoryPort,
        *,
        ttl_hours: int = 168,
    ) -> None:
        self._users = users
        self._ttl = timedelta(hours=ttl_hours)

    def execute(self, tenant_id: UUID, actor_user_id: UUID, user_id: UUID) -> PasswordSetup:
        current = self._users.get_by_id(tenant_id, user_id)
        if current is None:
            raise NotFoundError("User not found")
        if current.id == actor_user_id and current.status is not UserStatus.INVITED:
            raise ConflictError(
                "Para sua própria conta, use a alteração de senha no perfil pessoal"
            )
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + self._ttl
        invited = current.status is UserStatus.INVITED
        updated = self._users.set_invitation(
            tenant_id,
            user_id,
            token_hash=invitation_token_hash(token),
            expires_at=expires_at,
            invited=invited,
        )
        if updated is None:
            raise NotFoundError("User not found")
        self._users.add_audit(
            UserAuditLog(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                action="invitation_renewed" if invited else "password_reset_created",
                changes={"expires_at": expires_at.isoformat()},
            )
        )
        return PasswordSetup(updated, token, expires_at)


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
        actor_user_id: UUID,
        name: str | None,
        email: str | None,
        role: UserRole | None,
        status: UserStatus | None,
    ) -> User:
        current = self._users.get_by_id(tenant_id, user_id)
        if current is None:
            raise NotFoundError("User not found")
        role_changes = role is not None and role is not current.role
        status_changes = status is not None and status is not current.status
        if current.is_master and (role_changes or status_changes):
            raise ConflictError(
                "O administrador principal deve permanecer como administrador ativo"
            )
        removes_active_admin = (
            current.role is UserRole.ADMIN
            and current.status is UserStatus.ACTIVE
            and (
                (role_changes and role is not UserRole.ADMIN)
                or (status_changes and status is not UserStatus.ACTIVE)
            )
        )
        if removes_active_admin and self._users.count_active_admins_for_update(tenant_id) <= 1:
            raise ConflictError("A empresa precisa manter pelo menos um administrador ativo")
        if current.id == actor_user_id and (role_changes or status_changes):
            raise ConflictError(
                "Você não pode alterar seu próprio perfil ou status pela gestão da equipe"
            )

        changes: dict[str, object] = {}
        if name is not None and name.strip() != current.name:
            changes["name"] = {"before": current.name, "after": name.strip()}
        if email is not None and email.strip().lower() != current.email:
            changes["email"] = {"before": current.email, "after": email.strip().lower()}
        if role_changes and role is not None:
            changes["role"] = {"before": current.role.value, "after": role.value}
        if status_changes and status is not None:
            changes["status"] = {"before": current.status.value, "after": status.value}
        if not changes:
            return current

        updated = self._users.update(
            tenant_id,
            user_id,
            name=name,
            email=email,
            role=role,
            status=status,
            revoke_sessions=role_changes or status_changes,
        )
        if updated is None:
            raise NotFoundError("User not found")
        self._users.add_audit(
            UserAuditLog(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                action="user_updated",
                changes=changes,
            )
        )
        return updated


class RevokeUserSessionsUseCase:
    def __init__(self, users: UserRepositoryPort) -> None:
        self._users = users

    def execute(self, tenant_id: UUID, actor_user_id: UUID, user_id: UUID) -> User:
        user = self._users.revoke_sessions(tenant_id, user_id)
        if user is None:
            raise NotFoundError("User not found")
        self._users.add_audit(
            UserAuditLog(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                action="sessions_revoked",
                changes={},
            )
        )
        return user


class DeleteUserUseCase:
    def __init__(self, users: UserRepositoryPort) -> None:
        self._users = users

    def execute(self, tenant_id: UUID, actor_user_id: UUID, user_id: UUID) -> None:
        actor = self._users.get_by_id(tenant_id, actor_user_id)
        if actor is None:
            raise NotFoundError("User not found")
        if not actor.is_master:
            raise ForbiddenError("Somente o administrador principal pode excluir perfis")
        target = self._users.get_by_id(tenant_id, user_id)
        if target is None:
            raise NotFoundError("User not found")
        if target.is_master or target.id == actor_user_id:
            raise ConflictError("O administrador principal não pode ser excluído")

        self._users.add_audit(
            UserAuditLog(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                target_user_id=target.id,
                action="user_deleted",
                changes={
                    "name": target.name,
                    "email": target.email,
                    "role": target.role.value,
                    "status": target.status.value,
                },
            )
        )
        if not self._users.delete(tenant_id, user_id):
            raise NotFoundError("User not found")


class ListUserAuditUseCase:
    def __init__(self, users: UserRepositoryPort) -> None:
        self._users = users

    def execute(self, tenant_id: UUID, limit: int = 100) -> list[UserAuditLog]:
        return self._users.list_audit(tenant_id, limit)
