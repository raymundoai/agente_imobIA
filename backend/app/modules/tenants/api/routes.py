import re
import secrets
import unicodedata
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal, require_roles
from app.modules.billing_usage.commercial import CommercialEntitlementService
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.modules.tenants.api.schemas import (
    CreateTenantRequest,
    OnboardingStatusRequest,
    SignupRequest,
    SignupResponse,
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
from app.modules.users.adapters.repositories import SqlAlchemyUserRepository
from app.modules.users.domain.entities import UserRole
from app.shared.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.shared.security.rate_limit import client_ip

router = APIRouter(prefix="/tenants", tags=["tenants"])
signup_router = APIRouter(prefix="/signup", tags=["signup"])

RESERVED_SLUGS = {"admin", "api", "app", "plataforma", "platform", "suporte", "www"}


@signup_router.post("", response_model=SignupResponse, status_code=201)
def signup(
    payload: SignupRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> SignupResponse:
    """Self-service account: tenant, master admin and a free trial, then an open session."""

    if not container.settings.public_signup_enabled:
        raise ForbiddenError("O cadastro de novas contas está desativado")
    container.auth_rate_limiter.check_and_hit("signup_ip", client_ip(request))
    if SqlAlchemyUserRepository(session).list_by_email(str(payload.email)):
        raise ConflictError("Este email já tem uma conta. Entre com ele ou use outro email.")
    repository = SqlAlchemyTenantRepository(session)
    tenant, admin = CreateTenantUseCase(
        repository, container.password_hasher, container.event_bus
    ).execute(
        payload.company_name,
        _available_slug(repository, payload.company_name),
        payload.admin_name,
        str(payload.email),
        payload.password,
        settings={
            "onboarding": {"status": "pending"},
            # The AI agent introduces itself on behalf of this name even if the wizard is skipped.
            "profile": {"display_name": payload.company_name.strip()},
        },
    )
    trial = CommercialEntitlementService(session).start_trial(
        tenant.id, days=container.settings.trial_days
    )
    tokens = container.token_service
    return SignupResponse(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        access_token=tokens.create_access_token(
            admin.id, tenant.id, admin.role.value, admin.session_version
        ),
        refresh_token=tokens.create_refresh_token(
            admin.id, tenant.id, admin.role.value, admin.session_version
        ),
        trial_ends_at=trial.trial_ends_at or trial.cycle_ends_at,
    )


def _available_slug(repository: SqlAlchemyTenantRepository, company_name: str) -> str:
    """Internal company identifier (webhook URLs); users never type it."""

    base = (
        re.sub(
            r"[^a-z0-9]+",
            "-",
            unicodedata.normalize("NFKD", company_name).encode("ascii", "ignore").decode().lower(),
        )
        .strip("-")[:36]
        .strip("-")
        or "imobiliaria"
    )
    if len(base) < 3:
        base = f"imob-{base}"
    for suffix in ["", *(f"-{number}" for number in range(2, 50))]:
        candidate = f"{base}{suffix}"
        if candidate not in RESERVED_SLUGS and repository.get_by_slug(candidate) is None:
            return candidate
    return f"{base}-{secrets.token_hex(3)}"


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


@router.patch("/{tenant_id}/onboarding", response_model=TenantResponse)
def update_onboarding(
    tenant_id: UUID,
    payload: OnboardingStatusRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> TenantResponse:
    if tenant_id != principal.tenant_id:
        raise NotFoundError("Tenant not found")
    repository = SqlAlchemyTenantRepository(session)
    current = repository.get_by_id(principal.tenant_id)
    if current is None:
        raise NotFoundError("Tenant not found")
    settings = {**current.settings, "onboarding": {"status": payload.status}}
    tenant = UpdateTenantSettingsUseCase(repository).execute(principal.tenant_id, settings)
    return TenantResponse.from_domain(tenant)
