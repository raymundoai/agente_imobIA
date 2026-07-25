from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.tenants.domain.entities import Tenant
from app.modules.users.domain.entities import User


class TenantRepositoryPort(ABC):
    @abstractmethod
    def get_by_id(self, tenant_id: UUID) -> Tenant | None: ...

    @abstractmethod
    def get_by_slug(self, slug: str) -> Tenant | None: ...

    @abstractmethod
    def update_settings(self, tenant_id: UUID, settings: dict[str, object]) -> Tenant | None: ...


class TenantProvisioningPort(ABC):
    @abstractmethod
    def create_with_admin(self, tenant: Tenant, admin: User) -> None: ...
