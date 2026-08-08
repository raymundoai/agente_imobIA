import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from app.modules.contacts.ports import ContactUpsertPort
from app.modules.conversations.domain.entities import (
    Conversation,
    ConversationChannel,
    ConversationMode,
    Message,
    MessageAuthor,
    MessageDirection,
)
from app.modules.conversations.media import save_conversation_media
from app.modules.conversations.ports.repositories import (
    ConversationRepositoryPort,
    IncomingMessageData,
)
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.tenants.domain.entities import TenantStatus
from app.modules.tenants.ports.repositories import TenantRepositoryPort
from app.shared.errors.exceptions import (
    ApplicationError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
)
from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort


@dataclass(frozen=True, slots=True)
class WebhookOutcome:
    status: str
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    job_id: UUID | None = None


def lead_agent_is_active(settings: Mapping[str, Any], channel: str | None = None) -> bool:
    agents = settings.get("agents", {})
    if not isinstance(agents, Mapping):
        return True
    leads = agents.get("leads", {})
    if not isinstance(leads, Mapping):
        return True
    if str(leads.get("status", "active")).lower() == "inactive":
        return False
    if channel is None:
        return True
    channels = settings.get("channels", {})
    if not isinstance(channels, Mapping):
        return True
    channel_settings = channels.get(channel)
    if not isinstance(channel_settings, Mapping):
        return True
    configured_agents = channel_settings.get("agents")
    if configured_agents is None:
        return channel_settings.get("agent", "leads") == "leads"
    return isinstance(configured_agents, list) and "leads" in configured_agents


def phone_is_allowed_for_auto_reply(phone: str, allowed_phones: list[str]) -> bool:
    if not allowed_phones:
        return True
    incoming_variants = _whatsapp_phone_variants(phone)
    return any(
        incoming_variants & _whatsapp_phone_variants(allowed)
        for allowed in allowed_phones
    )


def _whatsapp_phone_variants(phone: str) -> set[str]:
    normalized = "".join(character for character in phone if character.isdigit())
    variants = {normalized}
    if normalized.startswith("55") and len(normalized) == 13 and normalized[4] == "9":
        variants.add(f"{normalized[:4]}{normalized[5:]}")
    elif normalized.startswith("55") and len(normalized) == 12:
        variants.add(f"{normalized[:4]}9{normalized[4:]}")
    return variants


class HandleIncomingWhatsappWebhookUseCase:
    def __init__(
        self,
        tenants: TenantRepositoryPort,
        conversations: ConversationRepositoryPort,
        credentials: ChannelCredentialsPort,
        channel: MessageChannelPort,
        events: EventBusPort,
        contacts: ContactUpsertPort,
    ) -> None:
        self._tenants = tenants
        self._conversations = conversations
        self._credentials = credentials
        self._channel = channel
        self._events = events
        self._contacts = contacts

    def execute(
        self,
        tenant_slug: str,
        webhook_secret: str | None,
        payload: Mapping[str, Any],
        *,
        auto_reply_enabled: bool = False,
        auto_reply_allowed_phones: list[str] | None = None,
        send_to_channel: bool = True,
        max_attempts: int = 5,
        debounce_seconds: int = 0,
        media_root: Path | None = None,
        media_max_bytes: int = 16 * 1024 * 1024,
    ) -> WebhookOutcome:
        tenant = self._tenants.get_by_slug(tenant_slug)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            raise NotFoundError("Webhook tenant not found")
        channel_credentials = self._credentials.get(tenant.slug)
        if channel_credentials is None:
            raise ConfigurationError("WhatsApp integration is not configured for tenant")
        if webhook_secret is None or not hmac.compare_digest(
            webhook_secret, channel_credentials.webhook_secret
        ):
            raise AuthenticationError("Invalid webhook secret")

        event_name = str(payload.get("event", "")).replace(".", "_").replace("-", "_").upper()
        if event_name != "MESSAGES_UPSERT":
            return WebhookOutcome(status="ignored_event")
        incoming = self._channel.receive_message(payload)
        resolved_group_name = incoming.conversation_name
        if incoming.is_group and not resolved_group_name:
            resolver = getattr(self._channel, "resolve_group_name", None)
            if callable(resolver):
                resolved_group_name = resolver(
                    channel_credentials, incoming.external_contact_id
                )
        connected_phone = _connected_whatsapp_phone(tenant.settings)
        if (
            not incoming.from_me
            and not incoming.is_group
            and connected_phone
            and whatsapp_phones_match(incoming.phone, connected_phone)
        ):
            return WebhookOutcome(status="ignored_tenant_owner")

        contact = (
            None
            if incoming.from_me or incoming.is_group
            else self._contacts.upsert(
                tenant.id,
                phone=incoming.phone,
                name=incoming.customer_name,
                source="whatsapp",
            )
        )
        attachments = incoming.attachments
        if attachments and media_root is not None:
            downloader = getattr(self._channel, "download_media", None)
            downloaded = downloader(channel_credentials, payload) if callable(downloader) else None
            if downloaded is not None:
                content, downloaded_mimetype = downloaded
                original = attachments[0]
                mimetype = str(original.get("mimetype") or downloaded_mimetype)
                filename = str(
                    original.get("fileName")
                    or f"{original.get('type', 'arquivo')}-{incoming.external_message_id}"
                )
                try:
                    stored = save_conversation_media(
                        media_root,
                        tenant.id,
                        UUID(int=0),
                        content=content,
                        content_type=mimetype,
                        original_filename=filename,
                        max_bytes=media_max_bytes,
                    )
                except ApplicationError:
                    stored = None
                if stored is not None:
                    stored["type"] = str(original.get("type") or stored["type"])
                    stored.update(
                        {
                            key: value
                            for key, value in original.items()
                            if key in {"seconds", "ptt", "isAnimated"}
                        }
                    )
                    attachments = [stored]
        result = self._conversations.record_inbound(
            tenant.id,
            IncomingMessageData(
                channel=ConversationChannel.WHATSAPP,
                external_message_id=incoming.external_message_id,
                external_contact_id=incoming.external_contact_id,
                phone=contact.phone if contact else incoming.phone,
                text=incoming.text,
                customer_name=None if incoming.from_me else incoming.customer_name,
                contact_id=contact.id if contact else None,
                attachments=attachments,
                enqueue_auto_reply=(
                    not incoming.from_me
                    and not incoming.is_group
                    and auto_reply_enabled
                    and lead_agent_is_active(tenant.settings, "whatsapp")
                    and phone_is_allowed_for_auto_reply(
                        incoming.phone, auto_reply_allowed_phones or []
                    )
                ),
                send_to_channel=send_to_channel,
                max_attempts=max_attempts,
                debounce_seconds=debounce_seconds,
                direction=(
                    MessageDirection.OUTBOUND if incoming.from_me else MessageDirection.INBOUND
                ),
                author_type=(MessageAuthor.HUMAN if incoming.from_me else MessageAuthor.CUSTOMER),
                record_usage=not incoming.from_me,
                is_group=incoming.is_group,
                group_name=(
                    resolved_group_name
                    or (f"Grupo WhatsApp · {incoming.phone[-6:]}" if incoming.is_group else None)
                ),
                sender_external_id=incoming.sender_external_id,
                sender_name=incoming.sender_name,
            ),
        )
        if not result.created:
            return WebhookOutcome(
                status="duplicate",
                conversation_id=result.conversation.id,
                message_id=result.message.id,
            )
        if result.conversation_created:
            self._events.publish(
                DomainEvent(
                    name="ConversationStarted",
                    tenant_id=tenant.id,
                    payload={"conversation_id": str(result.conversation.id)},
                )
            )
        self._events.publish(
            DomainEvent(
                name="MessageSent" if incoming.from_me else "MessageReceived",
                tenant_id=tenant.id,
                payload={
                    "conversation_id": str(result.conversation.id),
                    "message_id": str(result.message.id),
                },
            )
        )
        return WebhookOutcome(
            status="mirrored_outbound" if incoming.from_me else "processed",
            conversation_id=result.conversation.id,
            message_id=result.message.id,
            job_id=result.job_id,
        )


def _phone_digits(value: Any) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def whatsapp_phones_match(left: Any, right: Any) -> bool:
    return bool(_whatsapp_phone_variants(left) & _whatsapp_phone_variants(right))


def _whatsapp_phone_variants(value: Any) -> set[str]:
    digits = _phone_digits(value)
    variants = {digits} if digits else set()
    domestic = digits[2:] if digits.startswith("55") and len(digits) >= 12 else digits
    if domestic:
        variants.add(domestic)
        # WhatsApp may expose Brazilian mobile JIDs with or without the ninth digit.
        if len(domestic) == 11 and domestic[2] == "9":
            variants.add(domestic[:2] + domestic[3:])
        elif len(domestic) == 10 and domestic[2] in "6789":
            variants.add(domestic[:2] + "9" + domestic[2:])
    return variants


def _connected_whatsapp_phone(settings: Mapping[str, Any]) -> str:
    integrations = settings.get("integrations", {})
    if not isinstance(integrations, Mapping):
        return ""
    evolution = integrations.get("evolution", {})
    if not isinstance(evolution, Mapping):
        return ""
    return _phone_digits(evolution.get("connected_phone"))


class HandleIncomingTelegramWebhookUseCase:
    def __init__(
        self,
        tenants: TenantRepositoryPort,
        conversations: ConversationRepositoryPort,
        credentials: ChannelCredentialsPort,
        channel: MessageChannelPort,
        events: EventBusPort,
        contacts: ContactUpsertPort,
    ) -> None:
        self._tenants = tenants
        self._conversations = conversations
        self._credentials = credentials
        self._channel = channel
        self._events = events
        self._contacts = contacts

    def execute(
        self,
        tenant_slug: str,
        webhook_secret: str | None,
        payload: Mapping[str, Any],
        *,
        auto_reply_enabled: bool = False,
        send_to_channel: bool = True,
        max_attempts: int = 5,
        debounce_seconds: int = 0,
    ) -> WebhookOutcome:
        tenant = self._tenants.get_by_slug(tenant_slug)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            raise NotFoundError("Webhook tenant not found")
        credentials = self._credentials.get(tenant.slug)
        if credentials is None:
            raise ConfigurationError("Telegram integration is not configured for tenant")
        if webhook_secret is None or not hmac.compare_digest(
            webhook_secret, credentials.webhook_secret
        ):
            raise AuthenticationError("Invalid Telegram webhook secret")
        incoming = self._channel.receive_message(payload)
        if incoming.is_group:
            return WebhookOutcome(status="ignored_group")
        contact = self._contacts.upsert(
            tenant.id,
            phone=incoming.phone,
            name=incoming.customer_name,
            source="telegram",
        )
        result = self._conversations.record_inbound(
            tenant.id,
            IncomingMessageData(
                channel=ConversationChannel.TELEGRAM,
                external_message_id=incoming.external_message_id,
                external_contact_id=incoming.external_contact_id,
                phone=contact.phone,
                text=incoming.text,
                customer_name=incoming.customer_name,
                contact_id=contact.id,
                attachments=incoming.attachments,
                enqueue_auto_reply=auto_reply_enabled
                and lead_agent_is_active(tenant.settings, "telegram"),
                send_to_channel=send_to_channel,
                max_attempts=max_attempts,
                debounce_seconds=debounce_seconds,
            ),
        )
        if not result.created:
            return WebhookOutcome(
                status="duplicate",
                conversation_id=result.conversation.id,
                message_id=result.message.id,
            )
        if result.conversation_created:
            self._events.publish(
                DomainEvent(
                    name="ConversationStarted",
                    tenant_id=tenant.id,
                    payload={
                        "conversation_id": str(result.conversation.id),
                        "channel": "telegram",
                    },
                )
            )
        self._events.publish(
            DomainEvent(
                name="MessageReceived",
                tenant_id=tenant.id,
                payload={
                    "conversation_id": str(result.conversation.id),
                    "message_id": str(result.message.id),
                    "channel": "telegram",
                },
            )
        )
        return WebhookOutcome(
            status="processed",
            conversation_id=result.conversation.id,
            message_id=result.message.id,
            job_id=result.job_id,
        )


class ChangeConversationModeUseCase:
    def __init__(self, conversations: ConversationRepositoryPort, events: EventBusPort) -> None:
        self._conversations = conversations
        self._events = events

    def execute(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        mode: ConversationMode,
        assigned_user_id: UUID,
    ) -> Conversation:
        current = self._conversations.get_by_id(tenant_id, conversation_id)
        if current is None:
            raise NotFoundError("Conversation not found")
        if current.is_group and mode is ConversationMode.AI:
            raise ConflictError("O agente não pode ser ativado em grupos do WhatsApp")
        conversation = self._conversations.update_mode(
            tenant_id,
            conversation_id,
            mode,
            assigned_user_id if mode is ConversationMode.HUMAN else None,
        )
        if conversation is None:
            raise NotFoundError("Conversation not found")
        if mode is ConversationMode.HUMAN:
            self._events.publish(
                DomainEvent(
                    name="HumanHandoffRequested",
                    tenant_id=tenant_id,
                    payload={
                        "conversation_id": str(conversation_id),
                        "assigned_user_id": str(assigned_user_id),
                        "reason": "manual",
                    },
                )
            )
        return conversation


class SendHumanMessageUseCase:
    def __init__(
        self,
        tenants: TenantRepositoryPort,
        conversations: ConversationRepositoryPort,
        credentials: ChannelCredentialsPort,
        channel: MessageChannelPort,
        events: EventBusPort,
    ) -> None:
        self._tenants = tenants
        self._conversations = conversations
        self._credentials = credentials
        self._channel = channel
        self._events = events

    def execute(self, tenant_id: UUID, conversation_id: UUID, text: str) -> Message:
        tenant = self._tenants.get_by_id(tenant_id)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            raise NotFoundError("Tenant not found")
        conversation = self._conversations.get_by_id(tenant_id, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        if conversation.mode is not ConversationMode.HUMAN:
            raise ConflictError("Conversation must be in human mode")
        credentials = self._credentials.get(tenant.slug)
        if credentials is None:
            raise ConfigurationError("Canal de mensagens não configurado para esta empresa")

        recipient = (
            conversation.external_contact_id
            if conversation.is_group and conversation.external_contact_id
            else conversation.phone
        )
        sent = self._channel.send_message(credentials, recipient, text)
        message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            direction=MessageDirection.OUTBOUND,
            author_type=MessageAuthor.HUMAN,
            text=text,
            external_message_id=sent.external_message_id,
            channel=conversation.channel,
        )
        self._conversations.record_outbound(tenant_id, message)
        self._events.publish(
            DomainEvent(
                name="MessageSent",
                tenant_id=tenant_id,
                payload={
                    "conversation_id": str(conversation_id),
                    "message_id": str(message.id),
                },
            )
        )
        return message


class SendHumanMediaUseCase(SendHumanMessageUseCase):
    def execute_media(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        *,
        content: bytes,
        attachment: dict[str, Any],
        caption: str = "",
    ) -> Message:
        tenant = self._tenants.get_by_id(tenant_id)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            raise NotFoundError("Tenant not found")
        conversation = self._conversations.get_by_id(tenant_id, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        if conversation.mode is not ConversationMode.HUMAN:
            raise ConflictError("Conversation must be in human mode")
        credentials = self._credentials.get(tenant.slug)
        if credentials is None:
            raise ConfigurationError("Canal de mensagens não configurado para esta empresa")
        try:
            recipient = (
                conversation.external_contact_id
                if conversation.is_group and conversation.external_contact_id
                else conversation.phone
            )
            sent = self._channel.send_media(
                credentials,
                recipient,
                content=content,
                media_type=str(attachment["type"]),
                mimetype=str(attachment["mimetype"]),
                filename=str(attachment["fileName"]),
                caption=caption,
            )
        except NotImplementedError as exc:
            raise ConfigurationError("Este canal ainda não suporta envio de mídia") from exc
        message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            direction=MessageDirection.OUTBOUND,
            author_type=MessageAuthor.HUMAN,
            text=caption,
            external_message_id=sent.external_message_id,
            channel=conversation.channel,
            attachments=[attachment],
        )
        self._conversations.record_outbound(tenant_id, message)
        self._events.publish(
            DomainEvent(
                name="MessageSent",
                tenant_id=tenant_id,
                payload={
                    "conversation_id": str(conversation_id),
                    "message_id": str(message.id),
                    "media_type": str(attachment["type"]),
                },
            )
        )
        return message
