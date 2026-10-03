from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.shared.errors.exceptions import ApplicationError, TooManyRequestsError


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if isinstance(exc, TooManyRequestsError)
            else None
        )
        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content={
                "error": exc.code,
                "detail": str(exc),
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )
