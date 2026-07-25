from uuid import UUID

from app.modules.auth.ports.security import PasswordHasherPort
from app.modules.tenants.domain.entities import Tenant
from app.modules.tenants.ports.repositories import TenantProvisioningPort, TenantRepositoryPort
from app.modules.users.domain.entities import User, UserRole
from app.shared.errors.exceptions import NotFoundError
from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort


class CreateTenantUseCase:
    def __init__(
        self,
        provisioning: TenantProvisioningPort,
        passwords: PasswordHasherPort,
        events: EventBusPort,
    ) -> None:
        self._provisioning = provisioning
        self._passwords = passwords
        self._events = events

    def execute(
        self,
        name: str,
        slug: str,
        admin_name: str,
        admin_email: str,
        admin_password: str,
    ) -> tuple[Tenant, User]:
        tenant = Tenant(name=name.strip(), slug=slug.strip().lower())
        admin = User(
            tenant_id=tenant.id,
            name=admin_name.strip(),
            email=admin_email.strip().lower(),
            hashed_password=self._passwords.hash(admin_password),
            role=UserRole.ADMIN,
        )
        self._provisioning.create_with_admin(tenant, admin)
        self._events.publish(
            DomainEvent(
                name="TenantCreated",
                tenant_id=tenant.id,
                payload={"tenant_id": str(tenant.id), "admin_user_id": str(admin.id)},
            )
        )
        return tenant, admin


class GetTenantUseCase:
    def __init__(self, tenants: TenantRepositoryPort) -> None:
        self._tenants = tenants

    def execute(self, tenant_id: UUID) -> Tenant:
        tenant = self._tenants.get_by_id(tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return tenant


class UpdateTenantSettingsUseCase:
    def __init__(self, tenants: TenantRepositoryPort) -> None:
        self._tenants = tenants

    def execute(self, tenant_id: UUID, settings: dict[str, object]) -> Tenant:
        tenant = self._tenants.update_settings(tenant_id, settings)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return tenant
