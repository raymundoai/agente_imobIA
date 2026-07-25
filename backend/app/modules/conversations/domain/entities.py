from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class ConversationChannel(StrEnum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"


class ConversationStatus(StrEnum):
    OPEN = "open"
    WAITING_HUMAN = "waiting_human"
    CLOSED = "closed"


class ConversationMode(StrEnum):
    AI = "ai"
    HUMAN = "human"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageAuthor(StrEnum):
    CUSTOMER = "customer"
    AI = "ai"
    HUMAN = "human"
    SYSTEM = "system"


@dataclass(slots=True)
class Conversation:
    tenant_id: UUID
    phone: str
    id: UUID = field(default_factory=uuid4)
    contact_id: UUID | None = None
    channel: ConversationChannel = ConversationChannel.WHATSAPP
    external_contact_id: str | None = None
    customer_name: str | None = None
    status: ConversationStatus = ConversationStatus.OPEN
    mode: ConversationMode = ConversationMode.AI
    current_intent: str | None = None
    current_agent: str = "leads"
    assigned_user_id: UUID | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_message_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None


@dataclass(slots=True)
class Message:
    tenant_id: UUID
    conversation_id: UUID
    direction: MessageDirection
    author_type: MessageAuthor
    text: str
    id: UUID = field(default_factory=uuid4)
    channel: ConversationChannel = ConversationChannel.WHATSAPP
    attachments: list[dict[str, Any]] = field(default_factory=list)
    external_message_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
