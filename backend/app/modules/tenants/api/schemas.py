from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.tenants.domain.entities import Tenant


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    admin_name: str = Field(min_length=2, max_length=160)
    admin_email: EmailStr
    admin_password: str = Field(min_length=12, max_length=128)


class UpdateTenantSettingsRequest(BaseModel):
    settings: dict[str, Any]

    @model_validator(mode="after")
    def reject_unencrypted_credentials(self) -> "UpdateTenantSettingsRequest":
        sensitive_fragments = ("secret", "password", "token", "api_key", "credential")

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    if any(fragment in key.lower() for fragment in sensitive_fragments):
                        raise ValueError("Credentials require the encrypted integrations endpoint")
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(self.settings)
        return self


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    settings: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_domain(cls, tenant: Tenant) -> "TenantResponse":
        return cls(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            status=tenant.status.value,
            settings=tenant.settings,
            created_at=tenant.created_at,
        )
