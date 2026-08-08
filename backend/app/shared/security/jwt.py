from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.modules.auth.ports.security import TokenClaims, TokenServicePort
from app.shared.errors.exceptions import AuthenticationError


class JwtTokenService(TokenServicePort):
    def __init__(
        self,
        secret: str,
        algorithm: str,
        access_ttl_minutes: int,
        refresh_ttl_days: int,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._access_ttl = timedelta(minutes=access_ttl_minutes)
        self._refresh_ttl = timedelta(days=refresh_ttl_days)

    def _create(
        self,
        user_id: UUID,
        tenant_id: UUID,
        role: str,
        token_type: str,
        session_version: int = 0,
    ) -> str:
        now = datetime.now(UTC)
        ttl = self._access_ttl if token_type == "access" else self._refresh_ttl
        return jwt.encode(
            {
                "sub": str(user_id),
                "tenant_id": str(tenant_id),
                "role": role,
                "type": token_type,
                "ver": session_version,
                "iat": now,
                "exp": now + ttl,
            },
            self._secret,
            algorithm=self._algorithm,
        )

    def create_access_token(
        self, user_id: UUID, tenant_id: UUID, role: str, session_version: int = 0
    ) -> str:
        return self._create(user_id, tenant_id, role, "access", session_version)

    def create_refresh_token(
        self, user_id: UUID, tenant_id: UUID, role: str, session_version: int = 0
    ) -> str:
        return self._create(user_id, tenant_id, role, "refresh", session_version)

    def decode(self, token: str, expected_type: str) -> TokenClaims:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
            if payload.get("type") != expected_type:
                raise AuthenticationError("Invalid token type")
            return TokenClaims(
                user_id=UUID(payload["sub"]),
                tenant_id=UUID(payload["tenant_id"]),
                role=payload["role"],
                token_type=payload["type"],
                session_version=int(payload.get("ver", 0)),
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("Invalid or expired token") from exc
