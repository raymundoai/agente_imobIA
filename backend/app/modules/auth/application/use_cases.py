from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.modules.auth.ports.security import PasswordHasherPort, TokenServicePort
from app.modules.tenants.ports.repositories import TenantRepositoryPort
from app.modules.users.application.use_cases import invitation_token_hash
from app.modules.users.domain.entities import User, UserAuditLog, UserStatus
from app.modules.users.ports.repositories import UserRepositoryPort
from app.shared.errors.exceptions import AuthenticationError


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_slug: str | None = None


class LoginUseCase:
    def __init__(
        self,
        tenants: TenantRepositoryPort,
        users: UserRepositoryPort,
        passwords: PasswordHasherPort,
        tokens: TokenServicePort,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._passwords = passwords
        self._tokens = tokens

    def execute(self, tenant_slug: str, email: str, password: str) -> TokenPair:
        tenant = self._tenants.get_by_slug(tenant_slug)
        if tenant is None or tenant.status.value != "active":
            raise AuthenticationError("Invalid credentials")
        user = self._users.get_by_email(tenant.id, email)
        if (
            user is None
            or user.status is not UserStatus.ACTIVE
            or user.must_change_password
            or not self._passwords.verify(password, user.hashed_password)
        ):
            raise AuthenticationError("Invalid credentials")
        updated = self._users.record_login(user.tenant_id, user.id) or user
        return self._issue(updated)

    def _issue(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=self._tokens.create_access_token(
                user.id, user.tenant_id, user.role.value, user.session_version
            ),
            refresh_token=self._tokens.create_refresh_token(
                user.id, user.tenant_id, user.role.value, user.session_version
            ),
        )


class RefreshTokenUseCase:
    def __init__(self, users: UserRepositoryPort, tokens: TokenServicePort) -> None:
        self._users = users
        self._tokens = tokens

    def execute(self, refresh_token: str) -> TokenPair:
        claims = self._tokens.decode(refresh_token, expected_type="refresh")
        user = self._users.get_by_id(claims.tenant_id, claims.user_id)
        if (
            user is None
            or user.status is not UserStatus.ACTIVE
            or user.session_version != claims.session_version
        ):
            raise AuthenticationError("Invalid refresh token")
        return TokenPair(
            access_token=self._tokens.create_access_token(
                user.id, user.tenant_id, user.role.value, user.session_version
            ),
            refresh_token=self._tokens.create_refresh_token(
                user.id, user.tenant_id, user.role.value, user.session_version
            ),
        )


class AcceptInvitationUseCase:
    def __init__(
        self,
        tenants: TenantRepositoryPort,
        users: UserRepositoryPort,
        passwords: PasswordHasherPort,
        tokens: TokenServicePort,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._passwords = passwords
        self._tokens = tokens

    def execute(self, token: str, password: str) -> TokenPair:
        user = self._users.get_by_invitation_hash(invitation_token_hash(token))
        if (
            user is None
            or user.status not in {UserStatus.ACTIVE, UserStatus.INVITED}
            or user.invitation_expires_at is None
            or user.invitation_expires_at <= datetime.now(UTC)
        ):
            raise AuthenticationError("Convite inválido ou expirado")
        updated = self._users.accept_invitation(
            user.id, hashed_password=self._passwords.hash(password)
        )
        if updated is None:
            raise AuthenticationError("Convite inválido ou expirado")
        tenant = self._tenants.get_by_id(updated.tenant_id)
        if tenant is None or tenant.status.value != "active":
            raise AuthenticationError("Convite inválido ou expirado")
        self._users.add_audit(
            UserAuditLog(
                tenant_id=updated.tenant_id,
                actor_user_id=updated.id,
                target_user_id=updated.id,
                action="password_defined",
                changes={},
            )
        )
        return TokenPair(
            access_token=self._tokens.create_access_token(
                updated.id,
                updated.tenant_id,
                updated.role.value,
                updated.session_version,
            ),
            refresh_token=self._tokens.create_refresh_token(
                updated.id,
                updated.tenant_id,
                updated.role.value,
                updated.session_version,
            ),
            tenant_slug=tenant.slug,
        )


class ChangePasswordUseCase:
    def __init__(
        self,
        users: UserRepositoryPort,
        passwords: PasswordHasherPort,
        tokens: TokenServicePort,
    ) -> None:
        self._users = users
        self._passwords = passwords
        self._tokens = tokens

    def execute(
        self,
        tenant_id: UUID,
        user_id: UUID,
        current_password: str,
        new_password: str,
    ) -> TokenPair:
        user = self._users.get_by_id(tenant_id, user_id)
        if user is None or not self._passwords.verify(current_password, user.hashed_password):
            raise AuthenticationError("Senha atual inválida")
        updated = self._users.change_password(
            tenant_id,
            user_id,
            hashed_password=self._passwords.hash(new_password),
        )
        if updated is None:
            raise AuthenticationError("Usuário não encontrado")
        self._users.add_audit(
            UserAuditLog(
                tenant_id=tenant_id,
                actor_user_id=user_id,
                target_user_id=user_id,
                action="password_changed",
                changes={},
            )
        )
        return TokenPair(
            access_token=self._tokens.create_access_token(
                updated.id,
                updated.tenant_id,
                updated.role.value,
                updated.session_version,
            ),
            refresh_token=self._tokens.create_refresh_token(
                updated.id,
                updated.tenant_id,
                updated.role.value,
                updated.session_version,
            ),
        )
