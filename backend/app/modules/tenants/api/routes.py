from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal, require_roles
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.modules.tenants.api.schemas import (
    CreateTenantRequest,
    TenantResponse,
    UpdateTenantAgentsRequest,
    UpdateTenantChannelsRequest,
    UpdateTenantProfileRequest,
    UpdateTenantSettingsRequest,
)
from app.modules.tenants.application.use_cases import (
    CreateTenantUseCase,
    GetTenantUseCase,
    UpdateTenantSettingsUseCase,
)
from app.modules.users.domain.entities import UserRole
from app.shared.errors.exceptions import ForbiddenError, NotFoundError

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=201)
def create_tenant(
    payload: CreateTenantRequest,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> TenantResponse:
    if container.settings.app_env not in {"development", "test"}:
        raise ForbiddenError("Tenant provisioning is restricted to the platform administration")
    tenant, _ = CreateTenantUseCase(
        SqlAlchemyTenantRepository(session), container.password_hasher, container.event_bus
    ).execute(
        payload.name,
        payload.slug,
        payload.admin_name,
        payload.admin_email,
        payload.admin_password,
    )
    return TenantResponse.from_domain(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> TenantResponse:
    if tenant_id != principal.tenant_id:
        raise NotFoundError("Tenant not found")
    tenant = GetTenantUseCase(SqlAlchemyTenantRepository(session)).execute(principal.tenant_id)
    return TenantResponse.from_domain(tenant)


@router.patch("/{tenant_id}/settings", response_model=TenantResponse)
def update_settings(
    tenant_id: UUID,
    payload: UpdateTenantSettingsRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> TenantResponse:
    if tenant_id != principal.tenant_id:
        raise NotFoundError("Tenant not found")
    tenant = UpdateTenantSettingsUseCase(SqlAlchemyTenantRepository(session)).execute(
        principal.tenant_id, payload.settings
    )
    return TenantResponse.from_domain(tenant)


@router.patch("/{tenant_id}/settings/agents", response_model=TenantResponse)
def update_agents_settings(
    tenant_id: UUID,
    payload: UpdateTenantAgentsRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> TenantResponse:
    if tenant_id != principal.tenant_id:
        raise NotFoundError("Tenant not found")
    repository = SqlAlchemyTenantRepository(session)
    current = repository.get_by_id(principal.tenant_id)
    if current is None:
        raise NotFoundError("Tenant not found")
    settings = {**current.settings, "agents": payload.agents.model_dump()}
    tenant = UpdateTenantSettingsUseCase(repository).execute(principal.tenant_id, settings)
    return TenantResponse.from_domain(tenant)


@router.patch("/{tenant_id}/settings/channels", response_model=TenantResponse)
def update_channels_settings(
    tenant_id: UUID,
    payload: UpdateTenantChannelsRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> TenantResponse:
    if tenant_id != principal.tenant_id:
        raise NotFoundError("Tenant not found")
    repository = SqlAlchemyTenantRepository(session)
    current = repository.get_by_id(principal.tenant_id)
    if current is None:
        raise NotFoundError("Tenant not found")
    settings = {**current.settings, "channels": payload.channels.model_dump()}
    tenant = UpdateTenantSettingsUseCase(repository).execute(principal.tenant_id, settings)
    return TenantResponse.from_domain(tenant)


@router.patch("/{tenant_id}/settings/profile", response_model=TenantResponse)
def update_profile_settings(
    tenant_id: UUID,
    payload: UpdateTenantProfileRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> TenantResponse:
    if tenant_id != principal.tenant_id:
        raise NotFoundError("Tenant not found")
    repository = SqlAlchemyTenantRepository(session)
    current = repository.get_by_id(principal.tenant_id)
    if current is None:
        raise NotFoundError("Tenant not found")
    settings = {
        **current.settings,
        "profile": payload.profile.model_dump(exclude_unset=True),
    }
    tenant = UpdateTenantSettingsUseCase(repository).execute(principal.tenant_id, settings)
    return TenantResponse.from_domain(tenant)
