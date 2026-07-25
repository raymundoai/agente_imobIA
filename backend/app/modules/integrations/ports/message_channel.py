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
