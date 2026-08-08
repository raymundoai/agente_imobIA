from collections.abc import Mapping
from typing import Any

import httpx

from app.config import TelegramTenantSettings
from app.modules.integrations.domain.entities import ChannelCredentials
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.message_channel import (
    InboundChannelMessage,
    MessageChannelPort,
    SentChannelMessage,
)
from app.shared.errors.exceptions import ApplicationError, ExternalServiceError


class SettingsTelegramCredentialsProvider(ChannelCredentialsPort):
    def __init__(self, configs: dict[str, TelegramTenantSettings]) -> None:
        self._configs = {slug.lower(): config for slug, config in configs.items()}

    def get(self, tenant_slug: str) -> ChannelCredentials | None:
        config = self._configs.get(tenant_slug.lower())
        if config is None:
            return None
        return ChannelCredentials(
            base_url="https://api.telegram.org",
            instance=config.bot_username or "telegram",
            api_key=config.bot_token.get_secret_value(),
            webhook_secret=config.webhook_secret.get_secret_value(),
        )


class TelegramApiAdapter(MessageChannelPort):
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def receive_message(self, payload: Mapping[str, Any]) -> InboundChannelMessage:
        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, Mapping):
            raise ApplicationError("Telegram update has no supported message")
        chat = message.get("chat")
        sender = message.get("from")
        if not isinstance(chat, Mapping) or not isinstance(sender, Mapping):
            raise ApplicationError("Telegram message identity is missing")
        message_id = message.get("message_id")
        chat_id = chat.get("id")
        sender_id = sender.get("id")
        if not all(isinstance(value, int) for value in (message_id, chat_id, sender_id)):
            raise ApplicationError("Telegram message identifiers are invalid")
        text = message.get("text") or message.get("caption") or ""
        attachments = self._attachments(message)
        if not text and not attachments:
            raise ApplicationError("Telegram message has no supported content")
        name = " ".join(
            str(value).strip()
            for value in (sender.get("first_name"), sender.get("last_name"))
            if isinstance(value, str) and value.strip()
        )
        return InboundChannelMessage(
            external_message_id=f"{chat_id}:{message_id}",
            external_contact_id=str(chat_id),
            phone=f"telegram:{chat_id}",
            text=str(text),
            customer_name=name or (str(sender.get("username")) if sender.get("username") else None),
            attachments=attachments,
            is_group=str(chat.get("type")) in {"group", "supergroup", "channel"},
        )

    def send_message(
        self,
        credentials: ChannelCredentials,
        phone: str,
        text: str,
        *,
        idempotency_key: str | None = None,
    ) -> SentChannelMessage:
        chat_id = phone.removeprefix("telegram:")
        response = self._client.post(
            f"{credentials.base_url}/bot{credentials.api_key}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        if response.status_code >= 400:
            raise ExternalServiceError(f"Telegram API returned status {response.status_code}")
        payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not isinstance(message_id, int):
            raise ExternalServiceError("Telegram response did not include a message id")
        return SentChannelMessage(external_message_id=f"{chat_id}:{message_id}")

    def send_presence(
        self,
        credentials: ChannelCredentials,
        phone: str,
        *,
        delay_ms: int,
    ) -> None:
        chat_id = phone.removeprefix("telegram:")
        try:
            self._client.post(
                f"{credentials.base_url}/bot{credentials.api_key}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
            )
        except Exception:
            return None

    def get_me(self, credentials: ChannelCredentials) -> dict[str, Any]:
        response = self._client.get(f"{credentials.base_url}/bot{credentials.api_key}/getMe")
        if response.status_code >= 400:
            raise ExternalServiceError("Telegram bot token is invalid")
        payload = response.json()
        return payload.get("result", {}) if isinstance(payload, dict) else {}

    def set_webhook(self, credentials: ChannelCredentials, webhook_url: str) -> None:
        response = self._client.post(
            f"{credentials.base_url}/bot{credentials.api_key}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": credentials.webhook_secret,
                "allowed_updates": ["message", "edited_message"],
                "drop_pending_updates": False,
            },
        )
        if response.status_code >= 400 or not response.json().get("ok"):
            raise ExternalServiceError("Telegram webhook configuration failed")

    def webhook_info(self, credentials: ChannelCredentials) -> dict[str, Any]:
        response = self._client.get(
            f"{credentials.base_url}/bot{credentials.api_key}/getWebhookInfo"
        )
        if response.status_code >= 400:
            raise ExternalServiceError("Could not read Telegram webhook status")
        payload = response.json()
        return payload.get("result", {}) if isinstance(payload, dict) else {}

    @staticmethod
    def _attachments(message: Mapping[str, Any]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        for media_type in ("photo", "document", "audio", "voice", "video"):
            value = message.get(media_type)
            if value is not None:
                attachments.append({"type": media_type})
        return attachments
