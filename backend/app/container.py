from collections.abc import Generator
from dataclasses import dataclass

import httpx
from fastapi import Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.ai.adapters.document_parser import PlainTextDocumentParser
from app.modules.ai.adapters.openai_adapter import OpenAiAdapter
from app.modules.ai.domain.ports import DocumentParserPort
from app.modules.auth.ports.security import PasswordHasherPort, TokenServicePort
from app.modules.integrations.adapters.evolution_api import EvolutionApiAdapter
from app.modules.integrations.adapters.hubspot import HubSpotCrmAdapter
from app.modules.integrations.adapters.persistent_credentials import (
    PersistentEvolutionCredentialsProvider,
)
from app.modules.integrations.adapters.settings_crm_credentials import (
    SettingsCrmCredentialsProvider,
)
from app.modules.integrations.adapters.settings_platform_credentials import (
    SettingsPlatformCredentialsProvider,
)
from app.modules.integrations.adapters.tecimob import TecimobAdapter
from app.modules.integrations.adapters.telegram import (
    SettingsTelegramCredentialsProvider,
    TelegramApiAdapter,
)
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.crm import CrmCredentialsPort, CrmPort
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.integrations.ports.real_estate_platform import RealEstatePlatformPort
from app.modules.properties.media import (
    LocalPropertyImageStorage,
    PropertyImageStorage,
    S3PropertyImageStorage,
)
from app.shared.database.session import Database
from app.shared.events.in_memory import InMemoryEventBus
from app.shared.events.ports import EventBusPort
from app.shared.security.jwt import JwtTokenService
from app.shared.security.passwords import Argon2PasswordHasher


@dataclass(slots=True)
class Container:
    settings: Settings
    database: Database
    password_hasher: PasswordHasherPort
    token_service: TokenServicePort
    event_bus: EventBusPort
    channel_credentials: ChannelCredentialsPort
    message_channel: MessageChannelPort
    telegram_credentials: ChannelCredentialsPort
    telegram_channel: TelegramApiAdapter
    crm_credentials: CrmCredentialsPort
    crm: CrmPort
    tecimob_credentials: SettingsPlatformCredentialsProvider
    tecimob: RealEstatePlatformPort
    ai_provider: OpenAiAdapter | None
    document_parser: DocumentParserPort
    property_image_storage: PropertyImageStorage
    http_client: httpx.Client

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        http_client = httpx.Client(timeout=settings.evolution_timeout_seconds)
        database = Database(settings.database_url)
        ai_provider = (
            OpenAiAdapter(
                api_key=settings.openai_api_key.get_secret_value(),
                chat_model=settings.openai_chat_model,
                chat_reasoning_effort=settings.openai_chat_reasoning_effort,
                chat_max_output_tokens=settings.openai_chat_max_output_tokens,
                embedding_model=settings.openai_embedding_model,
                embedding_dimensions=settings.openai_embedding_dimensions,
                image_model=settings.openai_image_model,
                transcription_model=settings.openai_transcription_model,
                vision_model=settings.openai_vision_model,
            )
            if settings.openai_api_key is not None
            else None
        )
        if settings.property_storage_backend == "s3":
            if not settings.property_s3_bucket:
                raise ValueError("PROPERTY_S3_BUCKET is required for S3 storage")
            property_image_storage: PropertyImageStorage = S3PropertyImageStorage(
                bucket=settings.property_s3_bucket,
                endpoint_url=settings.property_s3_endpoint_url,
                region=settings.property_s3_region,
                access_key=(
                    settings.property_s3_access_key.get_secret_value()
                    if settings.property_s3_access_key
                    else None
                ),
                secret_key=(
                    settings.property_s3_secret_key.get_secret_value()
                    if settings.property_s3_secret_key
                    else None
                ),
            )
        else:
            property_image_storage = LocalPropertyImageStorage(settings.property_media_root)
        return cls(
            settings=settings,
            database=database,
            password_hasher=Argon2PasswordHasher(),
            token_service=JwtTokenService(
                secret=settings.jwt_secret.get_secret_value(),
                algorithm=settings.jwt_algorithm,
                access_ttl_minutes=settings.access_token_ttl_minutes,
                refresh_ttl_days=settings.refresh_token_ttl_days,
            ),
            event_bus=InMemoryEventBus(),
            channel_credentials=PersistentEvolutionCredentialsProvider(
                database, settings
            ),
            message_channel=EvolutionApiAdapter(
                http_client,
                retry_attempts=settings.integration_retry_attempts,
                retry_base_delay_seconds=settings.integration_retry_base_delay_seconds,
            ),
            telegram_credentials=SettingsTelegramCredentialsProvider(
                settings.telegram_tenant_configs
            ),
            telegram_channel=TelegramApiAdapter(http_client),
            crm_credentials=SettingsCrmCredentialsProvider(settings.hubspot_tenant_configs),
            crm=HubSpotCrmAdapter(
                http_client,
                api_version=settings.hubspot_api_version,
                retry_attempts=settings.integration_retry_attempts,
            ),
            tecimob_credentials=SettingsPlatformCredentialsProvider(
                settings.tecimob_tenant_configs
            ),
            tecimob=TecimobAdapter(
                http_client,
                retry_attempts=settings.integration_retry_attempts,
            ),
            ai_provider=ai_provider,
            document_parser=PlainTextDocumentParser(),
            property_image_storage=property_image_storage,
            http_client=http_client,
        )

    def close(self) -> None:
        self.http_client.close()
        self.database.dispose()


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_db_session(request: Request) -> Generator[Session, None, None]:
    yield from get_container(request).database.session()
