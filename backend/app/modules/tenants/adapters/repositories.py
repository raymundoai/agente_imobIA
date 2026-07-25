from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.tenants.adapters.models import TenantModel
from app.modules.tenants.domain.entities import Tenant, TenantStatus
from app.modules.tenants.ports.repositories import TenantProvisioningPort, TenantRepositoryPort
from app.modules.users.adapters.models import UserModel
from app.modules.users.domain.entities import User
from app.shared.errors.exceptions import ConflictError


def _to_domain(model: TenantModel) -> Tenant:
    return Tenant(
        id=model.id,
        name=model.name,
        slug=model.slug,
        status=TenantStatus(model.status),
        settings=model.settings,
        created_at=model.created_at,
    )


class SqlAlchemyTenantRepository(TenantRepositoryPort, TenantProvisioningPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        model = self._session.scalar(select(TenantModel).where(TenantModel.id == tenant_id))
        return _to_domain(model) if model else None

    def get_by_slug(self, slug: str) -> Tenant | None:
        model = self._session.scalar(select(TenantModel).where(TenantModel.slug == slug.lower()))
        return _to_domain(model) if model else None

    def update_settings(self, tenant_id: UUID, settings: dict[str, object]) -> Tenant | None:
        model = self._session.scalar(select(TenantModel).where(TenantModel.id == tenant_id))
        if model is None:
            return None
        model.settings = settings
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def create_with_admin(self, tenant: Tenant, admin: User) -> None:
        tenant_model = TenantModel(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            status=tenant.status.value,
            settings=tenant.settings,
            created_at=tenant.created_at,
        )
        user_model = UserModel.from_domain(admin)
        self._session.add_all([tenant_model, user_model])
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError("Tenant slug or administrator email already exists") from exc
