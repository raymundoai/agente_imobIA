from functools import lru_cache
from pathlib import Path

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
    openai_chat_model: str = "gpt-5.6-luna"
    openai_chat_reasoning_effort: str = Field(
        default="none",
        pattern="^(none|minimal|low|medium|high|xhigh|max)$",
    )
    openai_chat_max_output_tokens: int = Field(default=4_000, ge=512, le=128_000)
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    openai_vision_model: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = Field(default=1536, gt=0, le=2048)
    openai_image_model: str = "gpt-image-2"
    property_media_root: Path = Path("storage/property-images")
    conversation_media_root: Path = Path("storage/conversation-media")
    conversation_media_max_bytes: int = Field(default=16 * 1024 * 1024, gt=0)
    property_media_legacy_root: Path | None = None
    property_legacy_url_allowed_hosts: list[str] = Field(default_factory=list)
    property_storage_backend: str = Field(default="local", pattern="^(local|s3)$")
    property_s3_bucket: str | None = None
    property_s3_endpoint_url: str | None = None
    property_s3_region: str | None = None
    property_s3_access_key: SecretStr | None = None
    property_s3_secret_key: SecretStr | None = None
    property_image_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    property_video_max_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    property_image_max_files: int = Field(default=12, gt=0, le=50)
    ai_auto_reply_enabled: bool = False
    ai_auto_send_to_channel: bool = False
    ai_auto_reply_allowed_phones: list[str] = Field(default_factory=list)
    ai_reply_debounce_seconds: int = Field(default=8, ge=0, le=60)
    ai_typing_delay_ms_per_character: int = Field(default=35, ge=0, le=200)
    ai_typing_delay_min_ms: int = Field(default=500, ge=0, le=10000)
    ai_typing_delay_max_ms: int = Field(default=4000, ge=0, le=30000)
    ai_message_part_pause_ms: int = Field(default=1200, ge=0, le=10000)
    message_job_max_attempts: int = Field(default=5, ge=1, le=20)
    message_job_backoff_seconds: int = Field(default=5, ge=1, le=3600)
    message_job_stale_seconds: int = Field(default=300, ge=30, le=86400)
    capture_job_max_attempts: int = Field(default=3, ge=1, le=10)
    capture_job_backoff_seconds: int = Field(default=15, ge=1, le=3600)
    capture_job_stale_seconds: int = Field(default=180, ge=30, le=3600)
    capture_http_connect_timeout_seconds: float = Field(default=5, gt=0, le=30)
    capture_http_read_timeout_seconds: float = Field(default=20, gt=0, le=120)
    capture_search_cache_ttl_seconds: int = Field(default=86_400, ge=300, le=604_800)
    capture_standard_search_credits: int = Field(default=10, ge=0, le=100_000)
    capture_web_discovery_enabled: bool = True
    capture_web_discovery_model: str = "gpt-5.6-luna"
    capture_web_discovery_max_results: int = Field(default=6, ge=1, le=12)
    capture_web_discovery_max_output_tokens: int = Field(default=4_000, ge=512, le=16_000)
    integration_secret_key: SecretStr | None = None
    integration_secret_key_version: int = Field(default=1, ge=1, le=1000)
    integration_secret_previous_keys: list[SecretStr] = Field(default_factory=list)
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

    @field_validator(
        "conversation_media_root",
        "property_media_legacy_root",
        "property_s3_endpoint_url",
        "property_s3_region",
        mode="before",
    )
    @classmethod
    def empty_property_storage_value_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "property_s3_access_key",
        "property_s3_secret_key",
        mode="before",
    )
    @classmethod
    def empty_property_storage_secret_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        normalized = [origin.rstrip("/") for origin in value]
        if "*" in normalized:
            raise ValueError("CORS_ORIGINS cannot contain wildcard origins")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
