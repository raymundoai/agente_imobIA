from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.ai.adapters.repositories import (
    SqlAlchemyAiAuditLogRepository,
    SqlAlchemyKnowledgeRepository,
)
from app.modules.ai.application.use_cases import GenerateAiReplyUseCase
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.conversations.adapters.repositories import SqlAlchemyConversationRepository
from app.modules.conversations.api.schemas import (
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    SendHumanMessageRequest,
    UpdateConversationModeRequest,
    WebhookResponse,
)
from app.modules.conversations.application.use_cases import (
    ChangeConversationModeUseCase,
    HandleIncomingTelegramWebhookUseCase,
    HandleIncomingWhatsappWebhookUseCase,
    SendHumanMessageUseCase,
)
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.application.use_cases import LeadQualificationService
from app.modules.maintenance.adapters.repositories import SqlAlchemyMaintenanceTicketRepository
from app.modules.maintenance.application.use_cases import MaintenanceTicketingService
from app.modules.properties.adapters.repositories import SqlAlchemyPropertyRepository
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.shared.errors.exceptions import NotFoundError

webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])
router = APIRouter(prefix="/conversations", tags=["conversations"])


@webhook_router.post("/whatsapp/{tenant_slug}", response_model=WebhookResponse)
def whatsapp_webhook(
    tenant_slug: str,
    payload: dict[str, Any],
    webhook_secret_header: Annotated[str | None, Header(alias="X-ImobIA-Webhook-Secret")] = None,
    webhook_secret_query: Annotated[str | None, Query(alias="token")] = None,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> WebhookResponse:
    outcome = HandleIncomingWhatsappWebhookUseCase(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyConversationRepository(session),
        container.channel_credentials,
        container.message_channel,
        container.event_bus,
    ).execute(tenant_slug, webhook_secret_header or webhook_secret_query, payload)
    ai_response = None
    ai_error = None
    if (
        outcome.status == "processed"
        and outcome.conversation_id is not None
        and container.settings.ai_auto_reply_enabled
    ):
        if container.ai_provider is None:
            ai_error = "OpenAI integration is not configured"
        else:
            try:
                tenant = SqlAlchemyTenantRepository(session).get_by_slug(tenant_slug)
                if tenant is None:
                    raise NotFoundError("Webhook tenant not found")
                result = GenerateAiReplyUseCase(
                    SqlAlchemyTenantRepository(session),
                    SqlAlchemyConversationRepository(session),
                    container.ai_provider,
                    SqlAlchemyKnowledgeRepository(session),
                    SqlAlchemyAiAuditLogRepository(session),
                    container.channel_credentials,
                    container.message_channel,
                    container.event_bus,
                    LeadQualificationService(
                        SqlAlchemyTenantRepository(session),
                        SqlAlchemyLeadDemandRepository(session),
                        container.crm_credentials,
                        container.crm,
                        container.event_bus,
                    ),
                    MaintenanceTicketingService(
                        SqlAlchemyTenantRepository(session),
                        SqlAlchemyMaintenanceTicketRepository(session),
                        container.event_bus,
                    ),
                    SqlAlchemyPropertyRepository(session),
                ).execute(
                    tenant.id,
                    outcome.conversation_id,
                    send_to_channel=container.settings.ai_auto_send_to_channel,
                )
                ai_response = result.response_text
            except Exception as exc:
                ai_error = str(exc)
    return WebhookResponse(
        status=outcome.status,
        conversation_id=outcome.conversation_id,
        message_id=outcome.message_id,
        ai_response=ai_response,
        ai_error=ai_error,
    )


@webhook_router.post("/telegram/{tenant_slug}", response_model=WebhookResponse)
def telegram_webhook(
    tenant_slug: str,
    payload: dict[str, Any],
    webhook_secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> WebhookResponse:
    outcome = HandleIncomingTelegramWebhookUseCase(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyConversationRepository(session),
        container.telegram_credentials,
        container.telegram_channel,
        container.event_bus,
    ).execute(tenant_slug, webhook_secret, payload)
    ai_response = None
    ai_error = None
    if (
        outcome.status == "processed"
        and outcome.conversation_id is not None
        and container.settings.telegram_auto_reply_enabled
    ):
        if container.ai_provider is None:
            ai_error = "OpenAI integration is not configured"
        else:
            try:
                tenant = SqlAlchemyTenantRepository(session).get_by_slug(tenant_slug)
                if tenant is None:
                    raise NotFoundError("Webhook tenant not found")
                result = GenerateAiReplyUseCase(
                    SqlAlchemyTenantRepository(session),
                    SqlAlchemyConversationRepository(session),
                    container.ai_provider,
                    SqlAlchemyKnowledgeRepository(session),
                    SqlAlchemyAiAuditLogRepository(session),
                    container.telegram_credentials,
                    container.telegram_channel,
                    container.event_bus,
                    LeadQualificationService(
                        SqlAlchemyTenantRepository(session),
                        SqlAlchemyLeadDemandRepository(session),
                        container.crm_credentials,
                        container.crm,
                        container.event_bus,
                    ),
                    MaintenanceTicketingService(
                        SqlAlchemyTenantRepository(session),
                        SqlAlchemyMaintenanceTicketRepository(session),
                        container.event_bus,
                    ),
                    SqlAlchemyPropertyRepository(session),
                ).execute(tenant.id, outcome.conversation_id, send_to_channel=True)
                ai_response = result.response_text
            except Exception as exc:
                ai_error = str(exc)
    return WebhookResponse(
        status=outcome.status,
        conversation_id=outcome.conversation_id,
        message_id=outcome.message_id,
        ai_response=ai_response,
        ai_error=ai_error,
    )


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[ConversationResponse]:
    conversations = SqlAlchemyConversationRepository(session).list(
        principal.tenant_id, limit=limit, offset=offset
    )
    return [ConversationResponse.from_domain(item) for item in conversations]


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ConversationDetailResponse:
    repository = SqlAlchemyConversationRepository(session)
    conversation = repository.get_by_id(principal.tenant_id, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    messages = repository.list_messages(principal.tenant_id, conversation_id)
    response = ConversationResponse.from_domain(conversation)
    return ConversationDetailResponse(
        **response.model_dump(),
        messages=[MessageResponse.from_domain(message) for message in messages],
    )


@router.patch("/{conversation_id}/mode", response_model=ConversationResponse)
def update_conversation_mode(
    conversation_id: UUID,
    payload: UpdateConversationModeRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> ConversationResponse:
    conversation = ChangeConversationModeUseCase(
        SqlAlchemyConversationRepository(session), container.event_bus
    ).execute(
        principal.tenant_id,
        conversation_id,
        payload.mode,
        principal.user_id,
    )
    return ConversationResponse.from_domain(conversation)


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
def send_human_message(
    conversation_id: UUID,
    payload: SendHumanMessageRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> MessageResponse:
    conversation = SqlAlchemyConversationRepository(session).get_by_id(
        principal.tenant_id, conversation_id
    )
    if conversation is None:
        raise NotFoundError("Conversation not found")
    if conversation.channel.value == "telegram":
        credentials = container.telegram_credentials
        channel = container.telegram_channel
    else:
        credentials = container.channel_credentials
        channel = container.message_channel
    message = SendHumanMessageUseCase(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyConversationRepository(session),
        credentials,
        channel,
        container.event_bus,
    ).execute(principal.tenant_id, conversation_id, payload.text)
    return MessageResponse.from_domain(message)
