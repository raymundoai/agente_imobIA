from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.schemas import LoginRequest, RefreshRequest, TokenResponse
from app.modules.auth.application.use_cases import LoginUseCase, RefreshTokenUseCase
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
    )
