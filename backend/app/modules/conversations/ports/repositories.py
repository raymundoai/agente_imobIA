from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.modules.conversations.domain.entities import (
    Conversation,
    ConversationChannel,
    ConversationMode,
    Message,
)


@dataclass(frozen=True, slots=True)
class IncomingMessageData:
    channel: ConversationChannel
    external_message_id: str
    external_contact_id: str
    phone: str
    text: str
    customer_name: str | None
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class InboundRecordResult:
    conversation: Conversation
    message: Message
    created: bool
    conversation_created: bool = False


class ConversationRepositoryPort(ABC):
    @abstractmethod
    def record_inbound(
        self, tenant_id: UUID, incoming: IncomingMessageData
    ) -> InboundRecordResult: ...

    @abstractmethod
    def record_outbound(self, tenant_id: UUID, message: Message) -> Message: ...

    @abstractmethod
    def list(self, tenant_id: UUID, *, limit: int, offset: int) -> list[Conversation]: ...

    @abstractmethod
    def get_by_id(self, tenant_id: UUID, conversation_id: UUID) -> Conversation | None: ...

    @abstractmethod
    def list_messages(self, tenant_id: UUID, conversation_id: UUID) -> list[Message]: ...

    @abstractmethod
    def update_mode(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        mode: ConversationMode,
        assigned_user_id: UUID | None,
    ) -> Conversation | None: ...
