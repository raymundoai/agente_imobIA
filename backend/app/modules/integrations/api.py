import base64
import secrets
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.integrations.adapters.evolution_api import EvolutionManagerClient
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.shared.errors.exceptions import ConfigurationError, ExternalServiceError, NotFoundError

router = APIRouter(prefix="/integrations", tags=["integrations"])

SUPPORTED_SETUP_PROVIDERS = {
    "kenlo": {
        "name": "Kenlo",
        "category": "Gestão",
        "required_items": [
            "Confirmação de acesso à API REST oficial",
            "Credenciais de sandbox ou produção",
            "Base URL do ambiente liberado",
            "Escopos para imóveis, contatos, leads e atividades",
            "Documentação de limites de uso e webhooks",
        ],
        "target_resources": ["imóveis", "contatos", "leads", "atividades"],
    },
    "tecimob": {
        "name": "Tecimob",
        "category": "Gestão",
        "required_items": [
            "Documentação técnica da API aberta",
            "Token/chave de API do cliente",
            "Confirmação de permissões do plano contratado",
            "Endpoints para imóveis, leads e contatos",
            "Regras de webhook ou rotina de sincronização",
        ],
        "target_resources": ["imóveis", "contatos", "leads"],
    },
    "jetimob": {
        "name": "Jetimob",
        "category": "Gestão",
        "required_items": [
            "Confirmação de que o plano libera chaves de API",
            "Chaves ou token de API",
            "Base URL e documentação do ambiente",
            "Endpoints de imóveis ativos, leads e contatos",
            "Política de sincronização e limites de consulta",
        ],
        "target_resources": ["imóveis", "contatos", "leads"],
    },
    "orulo": {
        "name": "Órulo",
        "category": "Captação",
        "required_items": [
            "Client ID",
            "Client Secret",
            "Tipo de autenticação autorizado",
            "Escopos para catálogo, detalhes e mídia dos imóveis",
            "Confirmação de permissão para uso como CRM/parceiro",
        ],
        "target_resources": ["empreendimentos", "unidades", "imagens", "descrições"],
    },
}


class EvolutionWhatsappResponse(BaseModel):
    instance: str
    status: str
    qrcode: str | None = None
    pairing_code: str | None = None
    connected_phone: str | None = None
    connected_name: str | None = None
    webhook_configured: bool = False


class IntegrationSetupSummary(BaseModel):
    provider: str
    name: str
    category: str
    status: str
    required_items: list[str]
    target_resources: list[str]
    notes: str | None = None


class IntegrationSetupRequest(BaseModel):
    provider: str = Field(min_length=2, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)


class PlatformConnectionStatusResponse(BaseModel):
    provider: str
    configured: bool
    status: str
    detail: str | None = None


class TelegramConnectionResponse(BaseModel):
    configured: bool
    status: str
    bot_id: str | None = None
    bot_username: str | None = None
    webhook_url: str | None = None
    pending_updates: int = 0
    last_error: str | None = None


@router.get("/setup", response_model=list[IntegrationSetupSummary])
def list_integration_setups(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[IntegrationSetupSummary]:
    tenant_repo = SqlAlchemyTenantRepository(session)
    tenant = tenant_repo.get_by_id(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Empresa não encontrada")
    setup_state = _get_setup_state(tenant.settings)
    return [
        _setup_summary(provider, metadata, setup_state.get(provider, {}))
        for provider, metadata in SUPPORTED_SETUP_PROVIDERS.items()
    ]


@router.post("/setup", response_model=IntegrationSetupSummary)
def request_integration_setup(
    payload: IntegrationSetupRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> IntegrationSetupSummary:
    provider = payload.provider.lower()
    metadata = SUPPORTED_SETUP_PROVIDERS.get(provider)
    if metadata is None:
        raise NotFoundError("Integração não suportada no MVP")

    tenant_repo = SqlAlchemyTenantRepository(session)
    tenant = tenant_repo.get_by_id(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Empresa não encontrada")

    updated_settings = _upsert_setup_state(
        tenant.settings,
        provider,
        {
            "status": "awaiting_credentials",
            "notes": payload.notes,
        },
    )
    tenant_repo.update_settings(tenant.id, updated_settings)
    return _setup_summary(provider, metadata, _get_setup_state(updated_settings).get(provider, {}))


@router.get("/tecimob/status", response_model=PlatformConnectionStatusResponse)
def get_tecimob_status(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PlatformConnectionStatusResponse:
    tenant_repo = SqlAlchemyTenantRepository(session)
    tenant = tenant_repo.get_by_id(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Empresa não encontrada")
    credentials = container.tecimob_credentials.get(tenant.slug)
    return PlatformConnectionStatusResponse(
        provider="tecimob",
        configured=credentials is not None,
        status="configured" if credentials is not None else "awaiting_credentials",
        detail=None if credentials is not None else "Chave API da Tecimob ainda não configurada",
    )


@router.post("/telegram/connect", response_model=TelegramConnectionResponse)
def connect_telegram(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> TelegramConnectionResponse:
    tenant = SqlAlchemyTenantRepository(session).get_by_id(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Empresa não encontrada")
    credentials = container.telegram_credentials.get(tenant.slug)
    if credentials is None:
        raise ConfigurationError("Telegram não configurado para esta empresa")
    if container.settings.backend_public_url is None:
        raise ConfigurationError("BACKEND_PUBLIC_URL é necessária para o webhook do Telegram")
    bot = container.telegram_channel.get_me(credentials)
    webhook_url = (
        f"{str(container.settings.backend_public_url).rstrip('/')}/webhooks/telegram/{tenant.slug}"
    )
    container.telegram_channel.set_webhook(credentials, webhook_url)
    info = container.telegram_channel.webhook_info(credentials)
    updated = dict(tenant.settings)
    integrations = dict(updated.get("integrations") or {})
    integrations["telegram"] = {
        "status": "connected",
        "bot_username": bot.get("username"),
        "webhook_configured": True,
    }
    updated["integrations"] = integrations
    SqlAlchemyTenantRepository(session).update_settings(tenant.id, updated)
    return _telegram_response(credentials is not None, bot, info)


@router.get("/telegram/status", response_model=TelegramConnectionResponse)
def telegram_status(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> TelegramConnectionResponse:
    tenant = SqlAlchemyTenantRepository(session).get_by_id(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Empresa não encontrada")
    credentials = container.telegram_credentials.get(tenant.slug)
    if credentials is None:
        return TelegramConnectionResponse(configured=False, status="not_configured")
    bot = container.telegram_channel.get_me(credentials)
    info = container.telegram_channel.webhook_info(credentials)
    return _telegram_response(True, bot, info)


@router.post("/tecimob/test", response_model=PlatformConnectionStatusResponse)
def test_tecimob_connection(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PlatformConnectionStatusResponse:
    tenant_repo = SqlAlchemyTenantRepository(session)
    tenant = tenant_repo.get_by_id(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Empresa não encontrada")
    credentials = container.tecimob_credentials.get(tenant.slug)
    if credentials is None:
        return PlatformConnectionStatusResponse(
            provider="tecimob",
            configured=False,
            status="awaiting_credentials",
            detail="Chave API da Tecimob ainda não configurada",
        )
    groups = container.tecimob.list_contact_groups(credentials)
    return PlatformConnectionStatusResponse(
        provider="tecimob",
        configured=True,
        status="connected",
        detail=f"Conexão validada. Grupos de clientes encontrados: {len(groups)}",
    )


@router.post("/evolution/whatsapp/connect", response_model=EvolutionWhatsappResponse)
def connect_whatsapp(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
    settings: Settings = Depends(get_settings),
) -> EvolutionWhatsappResponse:
    tenant_repo = SqlAlchemyTenantRepository(session)
    tenant = tenant_repo.get_by_id(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Empresa não encontrada")

    manager = _build_manager(container, settings)
    integration = _get_whatsapp_integration(tenant.settings)
    instance = str(integration.get("instance") or _instance_name(tenant.slug))
    webhook_secret = secrets.token_urlsafe(32)

    manager.ensure_instance(instance, tenant.slug, webhook_secret)
    connection_payload = manager.connect_instance(instance)
    qrcode = _extract_qrcode(connection_payload)
    pairing_code = _extract_first_string(
        connection_payload, ("pairingCode", "pairing_code", "code")
    )
    state_payload = _try_connection_state(manager, instance)
    status = _normalize_connection_status(state_payload) or ("pending" if qrcode else "created")

    updated_settings = _upsert_whatsapp_integration(
        tenant.settings,
        {
            **_without_sensitive_fields(integration),
            "provider": "evolution",
            "instance": instance,
            "status": status,
            "webhook_configured": bool(settings.backend_public_url),
            "connected_phone": _extract_first_string(
                state_payload, ("number", "phone", "connectedPhone", "owner")
            ),
            "connected_name": _extract_first_string(state_payload, ("name", "profileName")),
        },
    )
    tenant_repo.update_settings(tenant.id, updated_settings)

    return EvolutionWhatsappResponse(
        instance=instance,
        status=status,
        qrcode=qrcode,
        pairing_code=pairing_code,
        connected_phone=_extract_first_string(
            state_payload, ("number", "phone", "connectedPhone", "owner")
        ),
        connected_name=_extract_first_string(state_payload, ("name", "profileName")),
        webhook_configured=bool(settings.backend_public_url),
    )


@router.get("/evolution/whatsapp/status", response_model=EvolutionWhatsappResponse)
def get_whatsapp_status(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
    settings: Settings = Depends(get_settings),
) -> EvolutionWhatsappResponse:
    tenant_repo = SqlAlchemyTenantRepository(session)
    tenant = tenant_repo.get_by_id(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Empresa não encontrada")
    integration = _get_whatsapp_integration(tenant.settings)
    instance = str(integration.get("instance") or _instance_name(tenant.slug))

    if not integration.get("instance"):
        return EvolutionWhatsappResponse(instance=instance, status="not_configured")

    manager = _build_manager(container, settings)
    state_payload = manager.connection_state(instance)
    status = _normalize_connection_status(state_payload) or "pending"
    connected_phone = _extract_first_string(
        state_payload, ("number", "phone", "connectedPhone", "owner")
    )
    connected_name = _extract_first_string(state_payload, ("name", "profileName"))

    updated_settings = _upsert_whatsapp_integration(
        tenant.settings,
        {
            **_without_sensitive_fields(integration),
            "status": status,
            "connected_phone": connected_phone,
            "connected_name": connected_name,
        },
    )
    tenant_repo.update_settings(tenant.id, updated_settings)

    return EvolutionWhatsappResponse(
        instance=instance,
        status=status,
        connected_phone=connected_phone,
        connected_name=connected_name,
        webhook_configured=bool(integration.get("webhook_configured")),
    )


def _build_manager(container: Container, settings: Settings) -> EvolutionManagerClient:
    if settings.evolution_base_url is None or settings.evolution_api_key is None:
        raise ConfigurationError("Evolution API não configurada no backend")
    return EvolutionManagerClient(
        container.http_client,
        str(settings.evolution_base_url),
        settings.evolution_api_key.get_secret_value(),
        str(settings.backend_public_url) if settings.backend_public_url else None,
    )


def _telegram_response(
    configured: bool, bot: dict[str, Any], info: dict[str, Any]
) -> TelegramConnectionResponse:
    webhook_url = info.get("url")
    last_error = info.get("last_error_message")
    return TelegramConnectionResponse(
        configured=configured,
        status="connected" if webhook_url and not last_error else "pending",
        bot_id=str(bot.get("id")) if bot.get("id") is not None else None,
        bot_username=str(bot.get("username")) if bot.get("username") else None,
        webhook_url=str(webhook_url) if webhook_url else None,
        pending_updates=int(info.get("pending_update_count") or 0),
        last_error=str(last_error) if last_error else None,
    )


def _setup_summary(
    provider: str, metadata: dict[str, Any], state: dict[str, Any]
) -> IntegrationSetupSummary:
    notes = state.get("notes")
    return IntegrationSetupSummary(
        provider=provider,
        name=str(metadata["name"]),
        category=str(metadata["category"]),
        status=str(state.get("status") or "not_configured"),
        required_items=list(metadata["required_items"]),
        target_resources=list(metadata["target_resources"]),
        notes=notes if isinstance(notes, str) else None,
    )


def _get_setup_state(settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    integrations = settings.get("integrations")
    if not isinstance(integrations, dict):
        return {}
    setup = integrations.get("setup")
    if not isinstance(setup, dict):
        return {}
    return {key: value for key, value in setup.items() if isinstance(value, dict)}


def _upsert_setup_state(
    settings: dict[str, Any], provider: str, state: dict[str, Any]
) -> dict[str, Any]:
    updated = dict(settings)
    integrations = dict(updated.get("integrations") or {})
    setup = dict(integrations.get("setup") or {})
    setup[provider] = {
        **setup.get(provider, {}),
        **state,
    }
    integrations["setup"] = setup
    updated["integrations"] = integrations
    return updated


def _instance_name(tenant_slug: str) -> str:
    return f"imobia-{tenant_slug}-whatsapp"


def _get_whatsapp_integration(settings: dict[str, Any]) -> dict[str, Any]:
    integrations = settings.get("integrations")
    if not isinstance(integrations, dict):
        return {}
    evolution = integrations.get("evolution")
    return evolution if isinstance(evolution, dict) else {}


def _upsert_whatsapp_integration(
    settings: dict[str, Any], evolution: dict[str, Any]
) -> dict[str, Any]:
    updated = dict(settings)
    integrations = dict(updated.get("integrations") or {})
    integrations["evolution"] = evolution
    updated["integrations"] = integrations

    channels = dict(updated.get("channels") or {})
    whatsapp = dict(channels.get("whatsapp") or {})
    whatsapp["status"] = "connected" if evolution.get("status") == "connected" else "pending"
    channels["whatsapp"] = whatsapp
    updated["channels"] = channels
    return updated


def _without_sensitive_fields(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: nested
        for key, nested in value.items()
        if key.lower() not in {"webhook_secret", "api_key", "token", "secret", "password"}
    }


def _try_connection_state(manager: EvolutionManagerClient, instance: str) -> dict[str, Any]:
    try:
        return manager.connection_state(instance)
    except ExternalServiceError:
        return {}


def _normalize_connection_status(payload: dict[str, Any]) -> str | None:
    state = _extract_first_string(payload, ("state", "status", "connection", "instance.state"))
    if state is None:
        return None
    normalized = state.lower()
    if normalized in {"open", "connected", "online"}:
        return "connected"
    if normalized in {"close", "closed", "disconnected", "offline"}:
        return "disconnected"
    if normalized in {"connecting", "pending", "created"}:
        return "pending"
    return normalized


def _extract_qrcode(payload: dict[str, Any]) -> str | None:
    value = _extract_first_string(payload, ("base64", "qrcode", "qr", "code"))
    if value is None:
        return None
    if value.startswith("data:image"):
        return value
    if _looks_like_base64(value):
        return f"data:image/png;base64,{value}"
    return value


def _looks_like_base64(value: str) -> bool:
    try:
        base64.b64decode(value, validate=True)
    except ValueError:
        return False
    return len(value) > 80


def _extract_first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _extract_path(payload, key.split("."))
        if isinstance(value, str) and value:
            return value
    for nested in payload.values():
        if isinstance(nested, dict):
            found = _extract_first_string(nested, keys)
            if found:
                return found
    return None


def _extract_path(payload: dict[str, Any], path: list[str]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
