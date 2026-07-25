from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.contacts.service import ContactUpsertService
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
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.shared.errors.exceptions import NotFoundError

webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])
router = APIRouter(prefix="/conversations", tags=["conversations"])


@webhook_router.post("/whatsapp/{tenant_slug}", response_model=WebhookResponse)
def whatsapp_webhook(
    tenant_slug: str,
    payload: dict[str, Any],
    webhook_secret_header: Annotated[str | None, Header(alias="X-ImobIA-Webhook-Secret")] = None,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> WebhookResponse:
    outcome = HandleIncomingWhatsappWebhookUseCase(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyConversationRepository(session),
        container.channel_credentials,
        container.message_channel,
        container.event_bus,
        ContactUpsertService(session),
    ).execute(
        tenant_slug,
        webhook_secret_header,
        payload,
        auto_reply_enabled=container.settings.ai_auto_reply_enabled,
        send_to_channel=container.settings.ai_auto_send_to_channel,
        max_attempts=container.settings.message_job_max_attempts,
    )
    return WebhookResponse(
        status=outcome.status,
        conversation_id=outcome.conversation_id,
        message_id=outcome.message_id,
        job_id=outcome.job_id,
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
        ContactUpsertService(session),
    ).execute(
        tenant_slug,
        webhook_secret,
        payload,
        auto_reply_enabled=container.settings.telegram_auto_reply_enabled,
        send_to_channel=True,
        max_attempts=container.settings.message_job_max_attempts,
    )
    return WebhookResponse(
        status=outcome.status,
        conversation_id=outcome.conversation_id,
        message_id=outcome.message_id,
        job_id=outcome.job_id,
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
