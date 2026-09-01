from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.conversations.domain.entities import Conversation, ConversationMode, Message


class WebhookResponse(BaseModel):
    status: str
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    job_id: UUID | None = None


class ConversationResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    contact_id: UUID | None
    channel: str
    phone: str
    customer_name: str | None
    status: str
    mode: str
    current_intent: str | None
    current_agent: str
    assigned_user_id: UUID | None
    started_at: datetime
    last_message_at: datetime
    archived_at: datetime | None
    archived_by_user_id: UUID | None
    is_group: bool
    group_name: str | None
    last_message_text: str | None
    last_message_attachments: list[dict[str, Any]]
    last_message_direction: str | None

    @classmethod
    def from_domain(cls, conversation: Conversation) -> "ConversationResponse":
        return cls(
            id=conversation.id,
            tenant_id=conversation.tenant_id,
            contact_id=conversation.contact_id,
            channel=conversation.channel.value,
            phone=conversation.phone,
            customer_name=conversation.customer_name,
            status=conversation.status.value,
            mode=conversation.mode.value,
            current_intent=conversation.current_intent,
            current_agent=conversation.current_agent,
            assigned_user_id=conversation.assigned_user_id,
            started_at=conversation.started_at,
            last_message_at=conversation.last_message_at,
            archived_at=conversation.archived_at,
            archived_by_user_id=conversation.archived_by_user_id,
            is_group=conversation.is_group,
            group_name=conversation.group_name,
            last_message_text=conversation.last_message_text,
            last_message_attachments=conversation.last_message_attachments,
            last_message_direction=(
                conversation.last_message_direction.value
                if conversation.last_message_direction is not None
                else None
            ),
        )


class MessageResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    direction: str
    author_type: str
    text: str
    attachments: list[dict[str, Any]]
    external_message_id: str | None
    created_at: datetime
    sender_external_id: str | None
    sender_name: str | None

    @classmethod
    def from_domain(cls, message: Message) -> "MessageResponse":
        return cls(
            id=message.id,
            tenant_id=message.tenant_id,
            conversation_id=message.conversation_id,
            direction=message.direction.value,
            author_type=message.author_type.value,
            text=message.text,
            attachments=message.attachments,
            external_message_id=message.external_message_id,
            created_at=message.created_at,
            sender_external_id=message.sender_external_id,
            sender_name=message.sender_name,
        )


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class UpdateConversationModeRequest(BaseModel):
    mode: ConversationMode


class UpdateConversationArchiveRequest(BaseModel):
    archived: bool


class SendHumanMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
