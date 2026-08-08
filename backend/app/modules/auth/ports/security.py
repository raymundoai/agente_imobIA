from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: UUID
    tenant_id: UUID
    role: str
    token_type: str
    session_version: int = 0


class PasswordHasherPort(ABC):
    @abstractmethod
    def hash(self, plain_password: str) -> str: ...

    @abstractmethod
    def verify(self, plain_password: str, hashed_password: str) -> bool: ...


class TokenServicePort(ABC):
    @abstractmethod
    def create_access_token(
        self, user_id: UUID, tenant_id: UUID, role: str, session_version: int = 0
    ) -> str: ...

    @abstractmethod
    def create_refresh_token(
        self, user_id: UUID, tenant_id: UUID, role: str, session_version: int = 0
    ) -> str: ...

    @abstractmethod
    def decode(self, token: str, expected_type: str) -> TokenClaims: ...
