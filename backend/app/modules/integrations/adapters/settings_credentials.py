from app.config import EvolutionTenantSettings
from app.modules.integrations.domain.entities import ChannelCredentials
from app.modules.integrations.ports.credentials import ChannelCredentialsPort


class SettingsChannelCredentialsProvider(ChannelCredentialsPort):
    def __init__(self, configs: dict[str, EvolutionTenantSettings]) -> None:
        self._configs = {slug.lower(): value for slug, value in configs.items()}

    def get(self, tenant_slug: str) -> ChannelCredentials | None:
        config = self._configs.get(tenant_slug.lower())
        if config is None:
            return None
        return ChannelCredentials(
            base_url=str(config.base_url).rstrip("/"),
            instance=config.instance,
            api_key=config.api_key.get_secret_value(),
            webhook_secret=config.webhook_secret.get_secret_value(),
        )
