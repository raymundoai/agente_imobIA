from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.modules.users.domain.entities import User, UserRole, UserStatus


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: UserRole


class UpdateUserRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    role: UserRole | None = None
    status: UserStatus | None = None


class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    email: EmailStr
    role: UserRole
    status: UserStatus
    created_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            tenant_id=user.tenant_id,
            name=user.name,
            email=user.email,
            role=user.role,
            status=user.status,
            created_at=user.created_at,
        )
