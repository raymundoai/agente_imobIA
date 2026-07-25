import hmac
from collections.abc import Mapping
from dataclasses import dataclass
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
from app.modules.conversations.ports.repositories import (
    ConversationRepositoryPort,
    IncomingMessageData,
)
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.tenants.domain.entities import TenantStatus
from app.modules.tenants.ports.repositories import TenantRepositoryPort
from app.shared.errors.exceptions import (
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


def lead_agent_is_active(settings: Mapping[str, Any]) -> bool:
    agents = settings.get("agents", {})
    if not isinstance(agents, Mapping):
        return True
    leads = agents.get("leads", {})
    if not isinstance(leads, Mapping):
        return True
    return str(leads.get("status", "active")).lower() != "inactive"


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
        send_to_channel: bool = True,
        max_attempts: int = 5,
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
        if incoming.from_me:
            return WebhookOutcome(status="ignored_outbound")
        if incoming.is_group:
            return WebhookOutcome(status="ignored_group")

        contact = self._contacts.upsert(
            tenant.id,
            phone=incoming.phone,
            name=incoming.customer_name,
            source="whatsapp",
        )
        result = self._conversations.record_inbound(
            tenant.id,
            IncomingMessageData(
                channel=ConversationChannel.WHATSAPP,
                external_message_id=incoming.external_message_id,
                external_contact_id=incoming.external_contact_id,
                phone=contact.phone,
                text=incoming.text,
                customer_name=incoming.customer_name,
                contact_id=contact.id,
                attachments=incoming.attachments,
                enqueue_auto_reply=auto_reply_enabled and lead_agent_is_active(tenant.settings),
                send_to_channel=send_to_channel,
                max_attempts=max_attempts,
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
                name="MessageReceived",
                tenant_id=tenant.id,
                payload={
                    "conversation_id": str(result.conversation.id),
                    "message_id": str(result.message.id),
                },
            )
        )
        return WebhookOutcome(
            status="processed",
            conversation_id=result.conversation.id,
            message_id=result.message.id,
            job_id=result.job_id,
        )


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
                enqueue_auto_reply=auto_reply_enabled and lead_agent_is_active(tenant.settings),
                send_to_channel=send_to_channel,
                max_attempts=max_attempts,
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

        sent = self._channel.send_message(credentials, conversation.phone, text)
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
