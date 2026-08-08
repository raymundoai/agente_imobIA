from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.modules.users.domain.entities import User, UserAuditLog, UserRole, UserStatus


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: UserRole


class InviteUserRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    role: UserRole


class UpdateUserRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    role: UserRole | None = None
    status: Literal["active", "inactive"] | None = None


class UpdateSelfRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None


class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    email: EmailStr
    role: UserRole
    status: UserStatus
    is_master: bool
    must_change_password: bool
    invitation_expires_at: datetime | None
    invited_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            tenant_id=user.tenant_id,
            name=user.name,
            email=user.email,
            role=user.role,
            status=user.status,
            is_master=user.is_master,
            must_change_password=user.must_change_password,
            invitation_expires_at=user.invitation_expires_at,
            invited_at=user.invited_at,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class PasswordSetupResponse(BaseModel):
    user: UserResponse
    token: str
    expires_at: datetime


class UserAuditResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    target_user_id: UUID | None
    action: str
    changes: dict[str, object]
    created_at: datetime

    @classmethod
    def from_domain(cls, audit: UserAuditLog) -> "UserAuditResponse":
        return cls(
            id=audit.id,
            actor_user_id=audit.actor_user_id,
            target_user_id=audit.target_user_id,
            action=audit.action,
            changes=audit.changes,
            created_at=audit.created_at,
        )
