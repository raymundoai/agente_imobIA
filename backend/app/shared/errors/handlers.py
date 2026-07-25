from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.shared.errors.exceptions import ApplicationError


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "detail": str(exc),
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )
