from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    require_roles,
)
from app.modules.billing_usage.adapters.models import CommercialPlanModel
from app.modules.billing_usage.commercial import CommercialEntitlementService
from app.modules.users.adapters.models import UserModel
from app.modules.users.adapters.repositories import SqlAlchemyUserRepository
from app.modules.users.api.schemas import (
    CreateUserRequest,
    InviteUserRequest,
    PasswordSetupResponse,
    UpdateSelfRequest,
    UpdateUserRequest,
    UserAuditResponse,
    UserResponse,
)
from app.modules.users.application.use_cases import (
    CreateUserUseCase,
    DeleteUserUseCase,
    GeneratePasswordSetupUseCase,
    InviteUserUseCase,
    ListUserAuditUseCase,
    ListUsersUseCase,
    RevokeUserSessionsUseCase,
    UpdateUserUseCase,
)
from app.modules.users.domain.entities import UserRole, UserStatus
from app.shared.errors.exceptions import ConflictError, NotFoundError

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    payload: CreateUserRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> UserResponse:
    _ensure_user_capacity(session, principal.tenant_id)
    user = CreateUserUseCase(
        SqlAlchemyUserRepository(session), container.password_hasher, container.event_bus
    ).execute(
        principal.tenant_id,
        payload.name,
        payload.email,
        payload.password,
        payload.role,
        actor_user_id=principal.user_id,
    )
    return UserResponse.from_domain(user)


@router.post("/invitations", response_model=PasswordSetupResponse, status_code=201)
def invite_user(
    payload: InviteUserRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PasswordSetupResponse:
    _ensure_user_capacity(session, principal.tenant_id)
    setup = InviteUserUseCase(
        SqlAlchemyUserRepository(session),
        container.password_hasher,
        container.event_bus,
    ).execute(
        principal.tenant_id,
        principal.user_id,
        payload.name,
        payload.email,
        payload.role,
    )
    return PasswordSetupResponse(
        user=UserResponse.from_domain(setup.user),
        token=setup.token,
        expires_at=setup.expires_at,
    )


@router.get("/audit", response_model=list[UserAuditResponse])
def list_user_audit(
    limit: int = Query(default=50, ge=1, le=200),
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> list[UserAuditResponse]:
    audits = ListUserAuditUseCase(SqlAlchemyUserRepository(session)).execute(
        principal.tenant_id, limit
    )
    return [UserAuditResponse.from_domain(audit) for audit in audits]


@router.get("/me", response_model=UserResponse)
def get_current_user(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> UserResponse:
    user = SqlAlchemyUserRepository(session).get_by_id(principal.tenant_id, principal.user_id)
    if user is None:
        raise NotFoundError("User not found")
    return UserResponse.from_domain(user)


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    payload: UpdateSelfRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> UserResponse:
    user = UpdateUserUseCase(SqlAlchemyUserRepository(session)).execute(
        principal.tenant_id,
        principal.user_id,
        actor_user_id=principal.user_id,
        name=payload.name,
        email=str(payload.email) if payload.email is not None else None,
        role=None,
        status=None,
    )
    return UserResponse.from_domain(user)


@router.get("", response_model=list[UserResponse])
def list_users(
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN, UserRole.GESTOR)),
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
        actor_user_id=principal.user_id,
        name=payload.name,
        email=str(payload.email) if payload.email is not None else None,
        role=payload.role,
        status=UserStatus(payload.status) if payload.status is not None else None,
    )
    return UserResponse.from_domain(user)


@router.post("/{user_id}/password-setup", response_model=PasswordSetupResponse)
def generate_password_setup(
    user_id: UUID,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> PasswordSetupResponse:
    setup = GeneratePasswordSetupUseCase(SqlAlchemyUserRepository(session)).execute(
        principal.tenant_id, principal.user_id, user_id
    )
    return PasswordSetupResponse(
        user=UserResponse.from_domain(setup.user),
        token=setup.token,
        expires_at=setup.expires_at,
    )


@router.post("/{user_id}/revoke-sessions", response_model=UserResponse)
def revoke_user_sessions(
    user_id: UUID,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> UserResponse:
    user = RevokeUserSessionsUseCase(SqlAlchemyUserRepository(session)).execute(
        principal.tenant_id, principal.user_id, user_id
    )
    return UserResponse.from_domain(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: UUID,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> None:
    DeleteUserUseCase(SqlAlchemyUserRepository(session)).execute(
        principal.tenant_id, principal.user_id, user_id
    )


def _ensure_user_capacity(session: Session, tenant_id: UUID) -> None:
    commercial = CommercialEntitlementService(session)
    subscription = commercial.subscription(tenant_id)
    session.commit()
    if subscription.enforcement_mode != "enforce":
        return
    plan = session.get(CommercialPlanModel, subscription.plan_id)
    if plan is None:
        raise RuntimeError("Commercial plan not found")
    occupied = int(
        session.scalar(
            select(func.count()).where(
                UserModel.tenant_id == tenant_id,
                UserModel.status != UserStatus.INACTIVE.value,
            )
        )
        or 0
    )
    if occupied >= plan.max_users:
        raise ConflictError(
            f"O plano {plan.name} permite até {plan.max_users} usuários ativos ou convidados"
        )
