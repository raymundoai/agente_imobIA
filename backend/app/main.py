from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.container import Container
from app.modules.ai.api import ai_router, knowledge_router
from app.modules.auth.api.routes import router as auth_router
from app.modules.billing_usage.api import router as usage_router
from app.modules.contacts.api import router as contacts_router
from app.modules.conversations.api.routes import router as conversations_router
from app.modules.conversations.api.routes import webhook_router
from app.modules.dashboard.api import router as dashboard_router
from app.modules.integrations.api import router as integrations_router
from app.modules.leads.api import router as leads_router
from app.modules.messaging.api import router as messaging_router
from app.modules.platform.api import router as platform_router
from app.modules.properties.api import router as properties_router
from app.modules.tenants.api.routes import router as tenants_router
from app.modules.users.api.routes import router as users_router
from app.shared.errors.handlers import install_error_handlers
from app.shared.logging.config import configure_logging
from app.shared.logging.middleware import CorrelationIdMiddleware, TenantContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    container = Container.build(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        container.close()

    application = FastAPI(title=resolved.app_name, lifespan=lifespan)
    application.state.container = container
    install_error_handlers(application)
    application.add_middleware(CorrelationIdMiddleware)
    application.add_middleware(TenantContextMiddleware, token_service=container.token_service)
    if resolved.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=resolved.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(auth_router, prefix=resolved.api_prefix)
    application.include_router(ai_router, prefix=resolved.api_prefix)
    application.include_router(dashboard_router, prefix=resolved.api_prefix)
    application.include_router(knowledge_router, prefix=resolved.api_prefix)
    application.include_router(integrations_router, prefix=resolved.api_prefix)
    application.include_router(leads_router, prefix=resolved.api_prefix)
    application.include_router(messaging_router, prefix=resolved.api_prefix)
    application.include_router(properties_router, prefix=resolved.api_prefix)
    application.include_router(platform_router, prefix=resolved.api_prefix)
    application.include_router(webhook_router, prefix=resolved.api_prefix)
    application.include_router(conversations_router, prefix=resolved.api_prefix)
    application.include_router(contacts_router, prefix=resolved.api_prefix)
    application.include_router(tenants_router, prefix=resolved.api_prefix)
    application.include_router(usage_router, prefix=resolved.api_prefix)
    application.include_router(users_router, prefix=resolved.api_prefix)
    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
