from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

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


class LeadAgentSettings(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(default="Agente de Leads", min_length=2, max_length=80)
    status: Literal["active", "inactive"] = "active"
    handoff_rules: str = Field(
        default=(
            "Lead pronto para visita, pedido de negociação, dúvida complexa ou baixa "
            "confiança da IA."
        ),
        min_length=2,
        max_length=2000,
    )
    restrictions: str = Field(
        default=(
            "Não prometer disponibilidade, não negociar valores finais e não assumir "
            "compromisso em nome do corretor."
        ),
        min_length=2,
        max_length=2000,
    )
    transfer_message: str = Field(
        default="Vou acionar um corretor da equipe para seguir com as melhores opções.",
        min_length=2,
        max_length=500,
    )
    voice_tone: Literal["professional", "friendly", "consultative", "informal"] = "friendly"
    emoji_usage: Literal["none", "low", "moderate"] = "low"


class AgentsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    leads: LeadAgentSettings = Field(default_factory=LeadAgentSettings)


class UpdateTenantAgentsRequest(BaseModel):
    agents: AgentsSettings


class ChannelSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["connected", "pending", "disabled", "disconnected"] = "pending"
    agents: list[Literal["leads"]] = Field(default_factory=lambda: ["leads"], max_length=1)


class ChannelsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    whatsapp: ChannelSettings = Field(default_factory=ChannelSettings)
    telegram: ChannelSettings = Field(default_factory=ChannelSettings)


class UpdateTenantChannelsRequest(BaseModel):
    channels: ChannelsSettings


class BusinessDaySettings(BaseModel):
    enabled: bool = False
    start: str = Field(default="08:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="18:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    break_enabled: bool = False
    break_start: str = Field(default="12:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    break_end: str = Field(default="13:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def validate_schedule(self) -> "BusinessDaySettings":
        if self.enabled and self.start >= self.end:
            raise ValueError("O início do atendimento deve ser anterior ao fim")
        if self.enabled and self.break_enabled and not (
            self.start < self.break_start < self.break_end < self.end
        ):
            raise ValueError("O intervalo deve ficar dentro do horário de atendimento")
        return self


BusinessWeekday = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class BusinessHoursSettings(BaseModel):
    timezone: str = Field(default="America/Sao_Paulo", min_length=3, max_length=80)
    days: dict[BusinessWeekday, BusinessDaySettings]


class TenantProfileSettings(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    display_name: str | None = Field(default=None, max_length=160)
    legal_name: str | None = Field(default=None, max_length=200)
    document_type: Literal["cpf", "cnpj"] | None = None
    document_number: str | None = Field(default=None, max_length=18)
    business_hours: BusinessHoursSettings | None = None
    regions: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_document(self) -> "TenantProfileSettings":
        if not self.document_number:
            return self
        if self.document_type is None:
            raise ValueError("Informe se o documento é CPF ou CNPJ")
        digits = "".join(character for character in self.document_number if character.isdigit())
        if not _valid_brazilian_document(digits, self.document_type):
            raise ValueError(f"Informe um {self.document_type.upper()} válido")
        self.document_number = digits
        return self


class UpdateTenantProfileRequest(BaseModel):
    profile: TenantProfileSettings


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
            settings=_without_sensitive_settings(tenant.settings),
            created_at=tenant.created_at,
        )


def _without_sensitive_settings(value: Any) -> Any:
    sensitive_fragments = ("secret", "password", "token", "api_key", "credential")
    if isinstance(value, dict):
        return {
            key: _without_sensitive_settings(nested)
            for key, nested in value.items()
            if not any(fragment in key.lower() for fragment in sensitive_fragments)
        }
    if isinstance(value, list):
        return [_without_sensitive_settings(item) for item in value]
    return value


def _valid_brazilian_document(digits: str, document_type: str) -> bool:
    expected = 11 if document_type == "cpf" else 14
    if len(digits) != expected or len(set(digits)) == 1:
        return False
    if document_type == "cpf":
        for length in (9, 10):
            total = sum(
                int(digit) * (length + 1 - index)
                for index, digit in enumerate(digits[:length])
            )
            remainder = (total * 10) % 11
            if (0 if remainder == 10 else remainder) != int(digits[length]):
                return False
        return True
    for length, weights in (
        (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
    ):
        total = sum(
            int(digit) * weight
            for digit, weight in zip(digits[:length], weights, strict=True)
        )
        remainder = total % 11
        if (0 if remainder < 2 else 11 - remainder) != int(digits[length]):
            return False
    return True
