from functools import lru_cache

from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvolutionTenantSettings(BaseModel):
    base_url: HttpUrl
    instance: str = Field(min_length=1, max_length=160)
    api_key: SecretStr
    webhook_secret: SecretStr


class HubSpotTenantSettings(BaseModel):
    base_url: HttpUrl = "https://api.hubapi.com"  # type: ignore[assignment]
    access_token: SecretStr
    pipeline_id: str | None = None
    stage_ids: dict[str, str] = Field(default_factory=dict)
    owner_map: dict[str, str] = Field(default_factory=dict)


class TecimobTenantSettings(BaseModel):
    base_url: HttpUrl = "https://api.tecimob.com.br/v1"  # type: ignore[assignment]
    access_token: SecretStr


class TelegramTenantSettings(BaseModel):
    bot_token: SecretStr
    webhook_secret: SecretStr
    bot_username: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "ImobIA API"
    api_prefix: str = ""
    database_url: str
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = Field(default=15, gt=0, le=60)
    refresh_token_ttl_days: int = Field(default=7, gt=0, le=30)
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)
    backend_public_url: HttpUrl | None = None
    evolution_base_url: HttpUrl | None = None
    evolution_api_key: SecretStr | None = None
    evolution_version: str | None = None
    evolution_tenant_configs: dict[str, EvolutionTenantSettings] = Field(default_factory=dict)
    evolution_timeout_seconds: float = Field(default=10, gt=0, le=60)
    integration_retry_attempts: int = Field(default=3, ge=1, le=5)
    integration_retry_base_delay_seconds: float = Field(default=0.25, ge=0, le=5)
    hubspot_tenant_configs: dict[str, HubSpotTenantSettings] = Field(default_factory=dict)
    hubspot_api_version: str = "2026-03"
    tecimob_tenant_configs: dict[str, TecimobTenantSettings] = Field(default_factory=dict)
    telegram_tenant_configs: dict[str, TelegramTenantSettings] = Field(default_factory=dict)
    telegram_auto_reply_enabled: bool = True
    openai_api_key: SecretStr | None = None
    openai_chat_model: str = "gpt-5.5"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = Field(default=1536, gt=0, le=2048)
    ai_auto_reply_enabled: bool = False
    ai_auto_send_to_channel: bool = False
    platform_bootstrap_token: SecretStr | None = None

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_postgres(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must point to PostgreSQL")
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("backend_public_url", "evolution_base_url", mode="before")
    @classmethod
    def empty_url_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("evolution_api_key", mode="before")
    @classmethod
    def empty_secret_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
