from app.config import HubSpotTenantSettings
from app.modules.integrations.ports.crm import CrmCredentials, CrmCredentialsPort


class SettingsCrmCredentialsProvider(CrmCredentialsPort):
    def __init__(self, configs: dict[str, HubSpotTenantSettings]) -> None:
        self._configs = configs

    def get(self, tenant_slug: str) -> CrmCredentials | None:
        config = self._configs.get(tenant_slug)
        if config is None:
            return None
        return CrmCredentials(
            base_url=str(config.base_url).rstrip("/"),
            access_token=config.access_token.get_secret_value(),
            pipeline_id=config.pipeline_id,
            stage_ids=config.stage_ids,
            owner_map=config.owner_map,
        )
