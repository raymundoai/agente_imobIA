from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.contacts.service import ContactUpsertService
from app.modules.conversations.adapters.models import MessageModel
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
    SendHumanMediaUseCase,
    SendHumanMessageUseCase,
)
from app.modules.conversations.media import media_path, save_conversation_media
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
        auto_reply_allowed_phones=container.settings.ai_auto_reply_allowed_phones,
        send_to_channel=container.settings.ai_auto_send_to_channel,
        max_attempts=container.settings.message_job_max_attempts,
        debounce_seconds=container.settings.ai_reply_debounce_seconds,
        media_root=container.settings.conversation_media_root,
        media_max_bytes=container.settings.conversation_media_max_bytes,
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
        debounce_seconds=container.settings.ai_reply_debounce_seconds,
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
    if messages:
        latest = messages[-1]
        response.last_message_text = latest.text
        response.last_message_attachments = latest.attachments
        response.last_message_direction = latest.direction.value
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


@router.post("/{conversation_id}/media", response_model=MessageResponse, status_code=201)
async def send_human_media(
    conversation_id: UUID,
    file: UploadFile = File(...),
    caption: str = Form(default="", max_length=4096),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> MessageResponse:
    repository = SqlAlchemyConversationRepository(session)
    conversation = repository.get_by_id(principal.tenant_id, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    content = await file.read(container.settings.conversation_media_max_bytes + 1)
    attachment = save_conversation_media(
        container.settings.conversation_media_root,
        principal.tenant_id,
        conversation_id,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        original_filename=file.filename or "arquivo",
        max_bytes=container.settings.conversation_media_max_bytes,
    )
    credentials = (
        container.telegram_credentials
        if conversation.channel.value == "telegram"
        else container.channel_credentials
    )
    channel = (
        container.telegram_channel
        if conversation.channel.value == "telegram"
        else container.message_channel
    )
    message = SendHumanMediaUseCase(
        SqlAlchemyTenantRepository(session),
        repository,
        credentials,
        channel,
        container.event_bus,
    ).execute_media(
        principal.tenant_id,
        conversation_id,
        content=content,
        attachment=attachment,
        caption=caption.strip(),
    )
    return MessageResponse.from_domain(message)


@router.get("/{conversation_id}/messages/{message_id}/media/{attachment_index}")
def get_message_media(
    conversation_id: UUID,
    message_id: UUID,
    attachment_index: int,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> FileResponse:
    model = session.scalar(
        select(MessageModel).where(
            MessageModel.tenant_id == principal.tenant_id,
            MessageModel.conversation_id == conversation_id,
            MessageModel.id == message_id,
        )
    )
    if model is None or attachment_index < 0 or attachment_index >= len(model.attachments):
        raise NotFoundError("Mídia não encontrada")
    attachment = model.attachments[attachment_index]
    storage_key = attachment.get("storage_key")
    if not isinstance(storage_key, str):
        raise NotFoundError("Esta mídia não está armazenada localmente")
    path = media_path(container.settings.conversation_media_root, storage_key)
    return FileResponse(
        path,
        media_type=str(attachment.get("mimetype") or "application/octet-stream"),
        filename=str(attachment.get("fileName") or path.name),
    )
