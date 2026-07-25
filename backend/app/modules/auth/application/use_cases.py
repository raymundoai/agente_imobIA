from dataclasses import dataclass

from app.modules.auth.ports.security import PasswordHasherPort, TokenServicePort
from app.modules.tenants.ports.repositories import TenantRepositoryPort
from app.modules.users.domain.entities import User, UserStatus
from app.modules.users.ports.repositories import UserRepositoryPort
from app.shared.errors.exceptions import AuthenticationError


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


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
            or not self._passwords.verify(password, user.hashed_password)
        ):
            raise AuthenticationError("Invalid credentials")
        return self._issue(user)

    def _issue(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=self._tokens.create_access_token(user.id, user.tenant_id, user.role.value),
            refresh_token=self._tokens.create_refresh_token(
                user.id, user.tenant_id, user.role.value
            ),
        )


class RefreshTokenUseCase:
    def __init__(self, users: UserRepositoryPort, tokens: TokenServicePort) -> None:
        self._users = users
        self._tokens = tokens

    def execute(self, refresh_token: str) -> TokenPair:
        claims = self._tokens.decode(refresh_token, expected_type="refresh")
        user = self._users.get_by_id(claims.tenant_id, claims.user_id)
        if user is None or user.status is not UserStatus.ACTIVE:
            raise AuthenticationError("Invalid refresh token")
        return TokenPair(
            access_token=self._tokens.create_access_token(user.id, user.tenant_id, user.role.value),
            refresh_token=self._tokens.create_refresh_token(
                user.id, user.tenant_id, user.role.value
            ),
        )
