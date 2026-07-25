from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal, require_roles
from app.modules.users.adapters.repositories import SqlAlchemyUserRepository
from app.modules.users.api.schemas import CreateUserRequest, UpdateUserRequest, UserResponse
from app.modules.users.application.use_cases import (
    CreateUserUseCase,
    ListUsersUseCase,
    UpdateUserUseCase,
)
from app.modules.users.domain.entities import UserRole

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    payload: CreateUserRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> UserResponse:
    user = CreateUserUseCase(
        SqlAlchemyUserRepository(session), container.password_hasher, container.event_bus
    ).execute(principal.tenant_id, payload.name, payload.email, payload.password, payload.role)
    return UserResponse.from_domain(user)


@router.get("", response_model=list[UserResponse])
def list_users(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[UserResponse]:
    users = ListUsersUseCase(SqlAlchemyUserRepository(session)).execute(principal.tenant_id)
    return [UserResponse.from_domain(user) for user in users]


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> UserResponse:
    user = UpdateUserUseCase(SqlAlchemyUserRepository(session)).execute(
        principal.tenant_id,
        user_id,
        name=payload.name,
        role=payload.role,
        status=payload.status,
    )
    return UserResponse.from_domain(user)
