from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request

from app.modules.users.domain.entities import UserRole
from app.shared.errors.exceptions import AuthenticationError, ForbiddenError


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    user_id: UUID
    tenant_id: UUID
    role: UserRole


def get_current_principal(request: Request) -> CurrentPrincipal:
    if getattr(request.state, "auth_error", None):
        raise AuthenticationError("Invalid access token")
    try:
        return CurrentPrincipal(
            user_id=request.state.user_id,
            tenant_id=request.state.tenant_id,
            role=UserRole(request.state.user_role),
        )
    except (AttributeError, ValueError) as exc:
        raise AuthenticationError("Authentication required") from exc


def require_roles(*allowed: UserRole):
    def dependency(
        principal: CurrentPrincipal = Depends(get_current_principal),
    ) -> CurrentPrincipal:
        if principal.role not in allowed:
            raise ForbiddenError("Insufficient permissions")
        return principal

    return dependency
