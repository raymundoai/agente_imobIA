from abc import ABC, abstractmethod

from app.modules.integrations.domain.entities import ChannelCredentials


class ChannelCredentialsPort(ABC):
    @abstractmethod
    def get(self, tenant_slug: str) -> ChannelCredentials | None: ...
