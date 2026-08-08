import logging
import time
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.modules.auth.ports.security import TokenServicePort
from app.modules.users.adapters.models import UserModel
from app.modules.users.domain.entities import UserStatus
from app.shared.database.session import Database

logger = logging.getLogger("imobos.http")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-correlation-id")
        try:
            correlation_id = str(UUID(incoming)) if incoming else str(uuid4())
        except ValueError:
            correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-correlation-id"] = correlation_id
        logger.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "correlation_id": correlation_id,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response


class TenantContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, token_service: TokenServicePort, database: Database) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._tokens = token_service
        self._database = database

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.auth_error = None
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            try:
                claims = self._tokens.decode(authorization[7:], expected_type="access")
                with self._database.session_factory() as session:
                    user = session.get(UserModel, claims.user_id)
                if (
                    user is None
                    or user.tenant_id != claims.tenant_id
                    or user.status != UserStatus.ACTIVE.value
                    or user.role != claims.role
                    or user.session_version != claims.session_version
                ):
                    raise ValueError("stale user session")
                request.state.tenant_id = claims.tenant_id
                request.state.user_id = claims.user_id
                request.state.user_role = user.role
            except Exception:
                request.state.auth_error = "invalid_token"
        return await call_next(request)
