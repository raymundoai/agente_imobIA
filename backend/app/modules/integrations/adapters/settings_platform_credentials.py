from app.config import TecimobTenantSettings
from app.modules.integrations.ports.real_estate_platform import PlatformCredentials


class SettingsPlatformCredentialsProvider:
    def __init__(self, configs: dict[str, TecimobTenantSettings]) -> None:
        self._configs = configs

    def get(self, tenant_slug: str) -> PlatformCredentials | None:
        config = self._configs.get(tenant_slug)
        if config is None:
            return None
        return PlatformCredentials(
            base_url=str(config.base_url),
            access_token=config.access_token.get_secret_value(),
        )
