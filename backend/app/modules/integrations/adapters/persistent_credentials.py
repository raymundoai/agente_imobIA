from sqlalchemy import func, select

from app.config import Settings
from app.modules.integrations.adapters.settings_credentials import (
    SettingsChannelCredentialsProvider,
)
from app.modules.integrations.domain.entities import ChannelCredentials
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.tenants.adapters.models import TenantModel
from app.shared.database.session import Database
from app.shared.security.secrets import SecretCipher, integration_cipher


class PersistentEvolutionCredentialsProvider(ChannelCredentialsPort):
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.fallback = SettingsChannelCredentialsProvider(settings.evolution_tenant_configs)
        dedicated = (
            settings.integration_secret_key.get_secret_value()
            if settings.integration_secret_key
            else None
        )
        self.cipher = integration_cipher(
            settings.jwt_secret.get_secret_value(), dedicated
        )
        self.legacy_cipher = SecretCipher(settings.jwt_secret.get_secret_value())
        self.previous_ciphers = [
            SecretCipher(key.get_secret_value())
            for key in settings.integration_secret_previous_keys
        ]

    def get(self, tenant_slug: str) -> ChannelCredentials | None:
        if self.settings.evolution_base_url and self.settings.evolution_api_key:
            with self.database.session_factory() as session:
                tenant = session.scalar(
                    select(TenantModel).where(func.lower(TenantModel.slug) == tenant_slug.lower())
                )
                integration = (
                    ((tenant.settings.get("integrations") or {}).get("evolution") or {})
                    if tenant is not None
                    else {}
                )
                encrypted = integration.get("webhook_secret_encrypted")
                secret = self.cipher.decrypt(encrypted) if isinstance(encrypted, str) else None
                if secret is None and isinstance(encrypted, str):
                    secret = self.legacy_cipher.decrypt(encrypted)
                if secret is None and isinstance(encrypted, str):
                    secret = next(
                        (
                            value
                            for cipher in self.previous_ciphers
                            if (value := cipher.decrypt(encrypted)) is not None
                        ),
                        None,
                    )
                instance = integration.get("instance")
                if secret and instance:
                    return ChannelCredentials(
                        base_url=str(self.settings.evolution_base_url).rstrip("/"),
                        instance=str(instance),
                        api_key=self.settings.evolution_api_key.get_secret_value(),
                        webhook_secret=secret,
                    )
        return self.fallback.get(tenant_slug)
