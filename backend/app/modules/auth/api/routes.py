from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.api.schemas import (
    AcceptInvitationRequest,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.modules.auth.application.use_cases import (
    AcceptInvitationUseCase,
    ChangePasswordUseCase,
    LoginUseCase,
    RefreshTokenUseCase,
)
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.modules.users.adapters.repositories import SqlAlchemyUserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> TokenResponse:
    result = LoginUseCase(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyUserRepository(session),
        container.password_hasher,
        container.token_service,
    ).execute(payload.tenant_slug, payload.email, payload.password)
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        tenant_slug=result.tenant_slug,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> TokenResponse:
    result = RefreshTokenUseCase(
        SqlAlchemyUserRepository(session), container.token_service
    ).execute(payload.refresh_token)
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        tenant_slug=result.tenant_slug,
    )


@router.post("/accept-invitation", response_model=TokenResponse)
def accept_invitation(
    payload: AcceptInvitationRequest,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> TokenResponse:
    result = AcceptInvitationUseCase(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyUserRepository(session),
        container.password_hasher,
        container.token_service,
    ).execute(payload.token, payload.password)
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        tenant_slug=result.tenant_slug,
    )


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    payload: ChangePasswordRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> TokenResponse:
    result = ChangePasswordUseCase(
        SqlAlchemyUserRepository(session),
        container.password_hasher,
        container.token_service,
    ).execute(
        principal.tenant_id,
        principal.user_id,
        payload.current_password,
        payload.new_password,
    )
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
    )
