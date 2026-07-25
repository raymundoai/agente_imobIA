import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from app.modules.integrations.domain.entities import ChannelCredentials
from app.modules.integrations.ports.message_channel import (
    InboundChannelMessage,
    MessageChannelPort,
    SentChannelMessage,
)
from app.shared.errors.exceptions import ApplicationError, ExternalServiceError


class EvolutionManagerClient:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        api_key: str,
        backend_public_url: str | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._backend_public_url = backend_public_url.rstrip("/") if backend_public_url else None

    def ensure_instance(
        self, instance_name: str, tenant_slug: str, webhook_secret: str
    ) -> dict[str, Any]:
        payload = {
            "instanceName": instance_name,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
        }
        response = self._request("POST", "/instance/create", json=payload)
        response_payload = self._safe_json(response)
        if response.status_code == 403 and not self._is_instance_already_in_use(
            response_payload, instance_name
        ):
            raise ExternalServiceError("Evolution API key inválida ou sem permissão")
        if response.status_code not in (200, 201, 403, 409):
            raise ExternalServiceError(
                f"Evolution API retornou status {response.status_code} ao criar instância"
            )
        if self._backend_public_url:
            self.configure_webhook(instance_name, tenant_slug, webhook_secret)
        return response_payload

    def connect_instance(self, instance_name: str) -> dict[str, Any]:
        response = self._request("GET", f"/instance/connect/{instance_name}")
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Evolution API retornou status {response.status_code} ao gerar QR Code"
            )
        return self._safe_json(response)

    def connection_state(self, instance_name: str) -> dict[str, Any]:
        response = self._request("GET", f"/instance/connectionState/{instance_name}")
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Evolution API retornou status {response.status_code} ao consultar conexão"
            )
        return self._safe_json(response)

    def configure_webhook(
        self, instance_name: str, tenant_slug: str, webhook_secret: str
    ) -> dict[str, Any] | None:
        if not self._backend_public_url:
            return None
        webhook_url = (
            f"{self._backend_public_url}/webhooks/whatsapp/{tenant_slug}?token={webhook_secret}"
        )
        payload = {
            "webhook": {
                "enabled": True,
                "url": webhook_url,
                "webhookByEvents": False,
                "webhookBase64": False,
                "events": [
                    "MESSAGES_UPSERT",
                    "CONNECTION_UPDATE",
                    "QRCODE_UPDATED",
                ],
            }
        }
        response = self._request("POST", f"/webhook/set/{instance_name}", json=payload)
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Evolution API retornou status {response.status_code} ao configurar webhook"
            )
        return self._safe_json(response)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.request(
            method,
            f"{self._base_url}{path}",
            headers={"apikey": self._api_key},
            **kwargs,
        )

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {"data": payload}

    @classmethod
    def _is_instance_already_in_use(cls, payload: dict[str, Any], instance_name: str) -> bool:
        messages = cls._collect_messages(payload)
        return any(
            instance_name in message and "already in use" in message.lower() for message in messages
        )

    @classmethod
    def _collect_messages(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            messages: list[str] = []
            for item in value:
                messages.extend(cls._collect_messages(item))
            return messages
        if isinstance(value, dict):
            messages = []
            for nested in value.values():
                messages.extend(cls._collect_messages(nested))
            return messages
        return []


class EvolutionApiAdapter(MessageChannelPort):
    def __init__(
        self,
        client: httpx.Client,
        retry_attempts: int = 3,
        retry_base_delay_seconds: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay_seconds
        self._sleep = sleeper

    def receive_message(self, payload: Mapping[str, Any]) -> InboundChannelMessage:
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ApplicationError("Invalid Evolution webhook payload")
        key = data.get("key")
        if not isinstance(key, Mapping):
            raise ApplicationError("Evolution webhook message key is missing")
        external_id = key.get("id")
        remote_jid = key.get("remoteJid")
        if not isinstance(external_id, str) or not external_id:
            raise ApplicationError("Evolution external message id is missing")
        if not isinstance(remote_jid, str) or "@" not in remote_jid:
            raise ApplicationError("Evolution remote contact id is missing")

        message = data.get("message")
        message_map = message if isinstance(message, Mapping) else {}
        text = self._extract_text(message_map)
        attachments = self._extract_attachments(message_map)
        if not text and not attachments:
            raise ApplicationError("Evolution message has no supported content")

        phone = "".join(
            character for character in remote_jid.split("@", 1)[0] if character.isdigit()
        )
        if not phone:
            raise ApplicationError("Evolution contact phone is invalid")
        customer_name = data.get("pushName")
        return InboundChannelMessage(
            external_message_id=external_id,
            external_contact_id=remote_jid,
            phone=phone,
            text=text,
            customer_name=customer_name if isinstance(customer_name, str) else None,
            attachments=attachments,
            from_me=bool(key.get("fromMe", False)),
            is_group=remote_jid.endswith("@g.us"),
        )

    def send_message(
        self, credentials: ChannelCredentials, phone: str, text: str
    ) -> SentChannelMessage:
        url = f"{credentials.base_url}/message/sendText/{credentials.instance}"
        last_error: Exception | None = None
        for attempt in range(self._retry_attempts):
            try:
                response = self._client.post(
                    url,
                    headers={"apikey": credentials.api_key},
                    json={"number": phone, "text": text},
                )
                if response.status_code < 500:
                    response.raise_for_status()
                    payload = response.json()
                    external_id = payload.get("key", {}).get("id")
                    if not isinstance(external_id, str) or not external_id:
                        raise ExternalServiceError(
                            "Evolution API response did not include a message id"
                        )
                    return SentChannelMessage(external_message_id=external_id)
                last_error = ExternalServiceError(
                    f"Evolution API returned status {response.status_code}"
                )
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    break
            if attempt + 1 < self._retry_attempts:
                self._sleep(self._retry_base_delay * (2**attempt))
        raise ExternalServiceError("Evolution API message delivery failed") from last_error

    @staticmethod
    def _extract_text(message: Mapping[str, Any]) -> str:
        conversation = message.get("conversation")
        if isinstance(conversation, str):
            return conversation
        paths = (
            ("extendedTextMessage", "text"),
            ("imageMessage", "caption"),
            ("videoMessage", "caption"),
            ("documentMessage", "caption"),
            ("buttonsResponseMessage", "selectedDisplayText"),
        )
        for container_name, key in paths:
            container = message.get(container_name)
            if isinstance(container, Mapping) and isinstance(container.get(key), str):
                return str(container[key])
        list_response = message.get("listResponseMessage")
        if isinstance(list_response, Mapping):
            selection = list_response.get("singleSelectReply")
            if isinstance(selection, Mapping) and isinstance(selection.get("selectedRowId"), str):
                return str(selection["selectedRowId"])
        return ""

    @staticmethod
    def _extract_attachments(message: Mapping[str, Any]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        for media_type in ("imageMessage", "videoMessage", "audioMessage", "documentMessage"):
            value = message.get(media_type)
            if not isinstance(value, Mapping):
                continue
            attachment: dict[str, Any] = {"type": media_type.removesuffix("Message")}
            for key in ("mimetype", "fileName", "url", "fileLength"):
                if key in value:
                    attachment[key] = value[key]
            attachments.append(attachment)
        return attachments
