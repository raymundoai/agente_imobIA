from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.modules.integrations.domain.entities import ChannelCredentials


@dataclass(frozen=True, slots=True)
class InboundChannelMessage:
    external_message_id: str
    external_contact_id: str
    phone: str
    text: str
    customer_name: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    from_me: bool = False
    is_group: bool = False
    conversation_name: str | None = None
    sender_external_id: str | None = None
    sender_name: str | None = None


@dataclass(frozen=True, slots=True)
class SentChannelMessage:
    external_message_id: str


class MessageChannelPort(ABC):
    @abstractmethod
    def receive_message(self, payload: Mapping[str, Any]) -> InboundChannelMessage: ...

    @abstractmethod
    def send_message(
        self,
        credentials: ChannelCredentials,
        phone: str,
        text: str,
        *,
        idempotency_key: str | None = None,
    ) -> SentChannelMessage: ...

    def send_media(
        self,
        credentials: ChannelCredentials,
        phone: str,
        *,
        content: bytes,
        media_type: str,
        mimetype: str,
        filename: str,
        caption: str = "",
    ) -> SentChannelMessage:
        raise NotImplementedError("This channel does not support media")

    def send_presence(
        self,
        credentials: ChannelCredentials,
        phone: str,
        *,
        delay_ms: int,
    ) -> None:
        return None
