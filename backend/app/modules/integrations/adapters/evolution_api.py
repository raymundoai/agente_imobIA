import base64
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

    def instance_info(self, instance_name: str) -> dict[str, Any]:
        response = self._request(
            "GET", "/instance/fetchInstances", params={"instanceName": instance_name}
        )
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Evolution API retornou status {response.status_code} ao consultar instância"
            )
        return self._safe_json(response)

    def webhook_url(self, tenant_slug: str) -> str | None:
        if not self._backend_public_url:
            return None
        return f"{self._backend_public_url}/webhooks/whatsapp/{tenant_slug}"

    def configure_webhook(
        self, instance_name: str, tenant_slug: str, webhook_secret: str
    ) -> dict[str, Any] | None:
        webhook_url = self.webhook_url(tenant_slug)
        if webhook_url is None:
            return None
        payload = {
            "webhook": {
                "enabled": True,
                "url": webhook_url,
                "headers": {"X-ImobIA-Webhook-Secret": webhook_secret},
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

    def webhook_info(self, instance_name: str) -> dict[str, Any]:
        response = self._request("GET", f"/webhook/find/{instance_name}")
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Evolution API retornou status {response.status_code} ao consultar webhook"
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
        self._group_names: dict[tuple[str, str], tuple[float, str]] = {}

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

        is_group = remote_jid.endswith("@g.us")
        canonical_jid = self._canonical_conversation_jid(key, remote_jid, is_group)
        phone = self._jid_digits(canonical_jid)
        if not phone:
            raise ApplicationError("Evolution contact phone is invalid")
        customer_name = data.get("pushName")
        sender_jid = self._sender_jid(key, is_group)
        group_name = self._first_string(
            data.get("groupName"),
            data.get("subject"),
            payload.get("groupName"),
        )
        return InboundChannelMessage(
            external_message_id=external_id,
            external_contact_id=canonical_jid,
            phone=phone,
            text=text,
            customer_name=(
                group_name
                if is_group
                else customer_name if isinstance(customer_name, str) else None
            ),
            attachments=attachments,
            from_me=bool(key.get("fromMe", False)),
            is_group=is_group,
            conversation_name=group_name,
            sender_external_id=sender_jid,
            sender_name=customer_name if isinstance(customer_name, str) else None,
        )

    def resolve_group_name(
        self,
        credentials: ChannelCredentials,
        group_jid: str,
        *,
        cache_ttl_seconds: float = 300,
    ) -> str | None:
        cache_key = (credentials.instance, group_jid)
        now = time.monotonic()
        cached = self._group_names.get(cache_key)
        if cached is not None and now - cached[0] < cache_ttl_seconds:
            return cached[1]
        try:
            response = self._client.get(
                f"{credentials.base_url}/group/fetchAllGroups/{credentials.instance}",
                headers={"apikey": credentials.api_key},
                params={"getParticipants": "false"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError):
            return None
        groups = (
            payload
            if isinstance(payload, list)
            else payload.get("data", payload.get("groups", []))
            if isinstance(payload, Mapping)
            else []
        )
        if not isinstance(groups, list):
            return None
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            jid = group.get("id")
            subject = group.get("subject")
            if isinstance(jid, str) and isinstance(subject, str) and subject.strip():
                self._group_names[(credentials.instance, jid)] = (now, subject.strip())
        resolved = self._group_names.get(cache_key)
        return resolved[1] if resolved is not None else None

    def profile_picture_url(
        self, credentials: ChannelCredentials, phone: str
    ) -> str | None:
        try:
            response = self._client.post(
                f"{credentials.base_url}/chat/fetchProfilePictureUrl/{credentials.instance}",
                headers={"apikey": credentials.api_key},
                json={"number": phone},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError):
            return None
        url = payload.get("profilePictureUrl") if isinstance(payload, Mapping) else None
        return url if isinstance(url, str) and url.startswith(("https://", "http://")) else None

    @classmethod
    def _canonical_conversation_jid(
        cls, key: Mapping[str, Any], remote_jid: str, is_group: bool
    ) -> str:
        if is_group:
            return remote_jid
        candidates = (
            remote_jid,
            key.get("remoteJidAlt"),
            key.get("senderPn"),
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.endswith("@s.whatsapp.net"):
                return candidate
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate
        return remote_jid

    @classmethod
    def _sender_jid(cls, key: Mapping[str, Any], is_group: bool) -> str | None:
        if not is_group:
            return None
        candidates = (
            key.get("participant"),
            key.get("participantAlt"),
            key.get("participantPn"),
            key.get("senderPn"),
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.endswith("@s.whatsapp.net"):
                return candidate
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    @staticmethod
    def _jid_digits(jid: str) -> str:
        return "".join(character for character in jid.split("@", 1)[0] if character.isdigit())

    @staticmethod
    def _first_string(*values: Any) -> str | None:
        return next((value for value in values if isinstance(value, str) and value.strip()), None)

    def send_message(
        self,
        credentials: ChannelCredentials,
        phone: str,
        text: str,
        *,
        idempotency_key: str | None = None,
    ) -> SentChannelMessage:
        url = f"{credentials.base_url}/message/sendText/{credentials.instance}"
        try:
            response = self._client.post(
                url,
                headers={
                    "apikey": credentials.api_key,
                    **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
                },
                json={"number": phone, "text": text},
            )
            response.raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            # POST delivery is ambiguous after transport errors and 5xx responses.
            # The queue records delivery_unknown and requires reconciliation.
            raise ExternalServiceError("Evolution API message delivery is uncertain") from exc
        payload = response.json()
        external_id = payload.get("key", {}).get("id")
        if not isinstance(external_id, str) or not external_id:
            raise ExternalServiceError("Evolution API response did not include a message id")
        return SentChannelMessage(external_message_id=external_id)

    def send_presence(
        self,
        credentials: ChannelCredentials,
        phone: str,
        *,
        delay_ms: int,
    ) -> None:
        try:
            response = self._client.post(
                f"{credentials.base_url}/chat/sendPresence/{credentials.instance}",
                headers={"apikey": credentials.api_key},
                json={
                    "number": phone,
                    "presence": "composing",
                    "delay": max(0, delay_ms),
                },
            )
            response.raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError):
            # Presença é apenas cosmética e nunca deve impedir a entrega da mensagem.
            return None

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
        encoded = base64.b64encode(content).decode("ascii")
        if media_type == "audio":
            path = f"/message/sendWhatsAppAudio/{credentials.instance}"
            body: dict[str, Any] = {
                "number": phone,
                "audio": encoded,
                "encoding": True,
            }
        else:
            path = f"/message/sendMedia/{credentials.instance}"
            body = {
                "number": phone,
                "mediatype": media_type,
                "mimetype": mimetype,
                "media": encoded,
                "fileName": filename,
                "caption": caption,
            }
        try:
            response = self._client.post(
                f"{credentials.base_url}{path}",
                headers={"apikey": credentials.api_key},
                json=body,
            )
            response.raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            raise ExternalServiceError("Evolution API media delivery is uncertain") from exc
        payload = response.json()
        external_id = payload.get("key", {}).get("id")
        if not isinstance(external_id, str) or not external_id:
            raise ExternalServiceError("Evolution API response did not include a media message id")
        return SentChannelMessage(external_message_id=external_id)

    def download_media(
        self,
        credentials: ChannelCredentials,
        payload: Mapping[str, Any],
    ) -> tuple[bytes, str] | None:
        data = payload.get("data")
        if not isinstance(data, Mapping):
            return None
        response = self._client.post(
            f"{credentials.base_url}/chat/getBase64FromMediaMessage/{credentials.instance}",
            headers={"apikey": credentials.api_key},
            json={"message": dict(data), "convertToMp4": False},
        )
        if response.status_code >= 400:
            return None
        result = response.json()
        encoded = result.get("base64")
        if not isinstance(encoded, str) or not encoded:
            return None
        if "," in encoded and encoded.startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            return None
        mimetype = result.get("mimetype")
        return content, str(mimetype) if mimetype else "application/octet-stream"

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
        for media_type in (
            "imageMessage",
            "videoMessage",
            "audioMessage",
            "documentMessage",
            "stickerMessage",
        ):
            value = message.get(media_type)
            if not isinstance(value, Mapping):
                continue
            attachment: dict[str, Any] = {"type": media_type.removesuffix("Message")}
            for key in (
                "mimetype",
                "fileName",
                "url",
                "fileLength",
                "seconds",
                "ptt",
                "isAnimated",
                "mediaKey",
                "directPath",
            ):
                if key in value:
                    attachment[key] = value[key]
            attachments.append(attachment)
        return attachments
