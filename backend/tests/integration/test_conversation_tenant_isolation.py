from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.modules.integrations.domain.entities import ChannelCredentials
from app.modules.integrations.ports.message_channel import (
    InboundChannelMessage,
    MessageChannelPort,
    SentChannelMessage,
)
from tests.conftest import TEST_WEBHOOK_SECRET

pytestmark = pytest.mark.integration


class FakeMessageChannel(MessageChannelPort):
    def __init__(self, delegate: MessageChannelPort) -> None:
        self._delegate = delegate
        self.sent: list[tuple[str, str]] = []
        self.sent_media: list[dict[str, Any]] = []

    def receive_message(self, payload: dict[str, Any]) -> InboundChannelMessage:
        return self._delegate.receive_message(payload)

    def send_message(
        self, credentials: ChannelCredentials, phone: str, text: str
    ) -> SentChannelMessage:
        self.sent.append((phone, text))
        return SentChannelMessage(external_message_id=f"sent-{len(self.sent)}")

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
        self.sent_media.append(
            {
                "phone": phone,
                "content": content,
                "media_type": media_type,
                "mimetype": mimetype,
                "filename": filename,
                "caption": caption,
            }
        )
        return SentChannelMessage(external_message_id=f"media-{len(self.sent_media)}")


def _provision(client: TestClient, slug: str) -> tuple[str, str]:
    password = "valid-test-password-123"
    created = client.post(
        "/tenants",
        json={
            "name": slug,
            "slug": slug,
            "admin_name": "Admin",
            "admin_email": "admin@example.com",
            "admin_password": password,
        },
    )
    assert created.status_code == 201, created.text
    login = client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": "admin@example.com", "password": password},
    )
    assert login.status_code == 200
    return created.json()["id"], login.json()["access_token"]


def _receive(
    client: TestClient, slug: str, external_id: str = "same-external-id"
) -> dict[str, Any]:
    response = client.post(
        f"/webhooks/whatsapp/{slug}",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json={
            "event": "MESSAGES_UPSERT",
            "data": {
                "key": {
                    "id": external_id,
                    "remoteJid": "5511888888888@s.whatsapp.net",
                    "fromMe": False,
                },
                "message": {"conversation": "Olá"},
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_conversation_can_be_archived_and_inbound_message_restores_it(
    client: TestClient,
) -> None:
    _, token = _provision(client, "tenant-a")
    conversation_id = _receive(client, "tenant-a")["conversation_id"]
    auth = {"Authorization": f"Bearer {token}"}

    archived = client.patch(
        f"/conversations/{conversation_id}/archive",
        headers=auth,
        json={"archived": True},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] is not None
    assert archived.json()["archived_by_user_id"] is not None
    assert client.get("/conversations", headers=auth).json() == []
    archived_list = client.get("/conversations?archived=true", headers=auth)
    assert [item["id"] for item in archived_list.json()] == [conversation_id]

    _receive(client, "tenant-a", "new-external-id")
    active_list = client.get("/conversations", headers=auth).json()
    assert [item["id"] for item in active_list] == [conversation_id]
    assert active_list[0]["archived_at"] is None
    assert client.get("/conversations?archived=true", headers=auth).json() == []


def test_conversation_archiving_is_tenant_isolated(client: TestClient) -> None:
    _, token_a = _provision(client, "tenant-a")
    _, token_b = _provision(client, "tenant-b")
    conversation_id = _receive(client, "tenant-a")["conversation_id"]

    response = client.patch(
        f"/conversations/{conversation_id}/archive",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"archived": True},
    )
    assert response.status_code == 404
    active = client.get(
        "/conversations", headers={"Authorization": f"Bearer {token_a}"}
    ).json()
    assert [item["id"] for item in active] == [conversation_id]


def test_conversations_handoff_and_messages_are_tenant_isolated(
    client: TestClient, migrated_database: str
) -> None:
    tenant_a, token_a = _provision(client, "tenant-a")
    tenant_b, token_b = _provision(client, "tenant-b")
    conversation_a = _receive(client, "tenant-a")["conversation_id"]
    conversation_b = _receive(client, "tenant-b")["conversation_id"]
    assert conversation_a != conversation_b

    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}
    assert client.get(f"/conversations/{conversation_a}", headers=auth_b).status_code == 404
    cross_tenant_demand = client.post(
        "/leads/demands",
        headers=auth_b,
        json={
            "lead_name": "Tentativa cruzada",
            "phone": "5511888888888",
            "conversation_id": conversation_a,
            "purpose": "buy",
        },
    )
    assert cross_tenant_demand.status_code == 404
    assert (
        client.patch(
            f"/conversations/{conversation_a}/mode", headers=auth_b, json={"mode": "human"}
        ).status_code
        == 404
    )

    handoff = client.patch(
        f"/conversations/{conversation_a}/mode", headers=auth_a, json={"mode": "human"}
    )
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["mode"] == "human"
    assert handoff.json()["status"] == "waiting_human"

    fake_channel = FakeMessageChannel(client.app.state.container.message_channel)
    client.app.state.container.message_channel = fake_channel
    sent = client.post(
        f"/conversations/{conversation_a}/messages",
        headers=auth_a,
        json={"text": "Olá, sou o corretor responsável."},
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["author_type"] == "human"
    assert fake_channel.sent == [("5511888888888", "Olá, sou o corretor responsável.")]

    property_photo = b"\x89PNG\r\n\x1a\nproperty-photo"
    media = client.post(
        f"/conversations/{conversation_a}/media",
        headers=auth_a,
        data={"caption": "Casa com 3 quartos em Porto Alegre"},
        files={"file": ("fachada.png", property_photo, "image/png")},
    )
    assert media.status_code == 201, media.text
    assert media.json()["text"] == "Casa com 3 quartos em Porto Alegre"
    assert media.json()["attachments"][0]["type"] == "image"
    assert fake_channel.sent_media == [
        {
            "phone": "5511888888888",
            "content": property_photo,
            "media_type": "image",
            "mimetype": "image/png",
            "filename": "fachada.png",
            "caption": "Casa com 3 quartos em Porto Alegre",
        }
    ]

    detail_b = client.get(f"/conversations/{conversation_b}", headers=auth_b)
    assert detail_b.status_code == 200
    assert len(detail_b.json()["messages"]) == 1

    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        usage_counts = dict(
            connection.execute(
                text(
                    "SELECT tenant_id::text, count(*) "
                    "FROM usage_records WHERE tenant_id IN (:tenant_a, :tenant_b) "
                    "GROUP BY tenant_id"
                ),
                {"tenant_a": tenant_a, "tenant_b": tenant_b},
            ).all()
        )
    engine.dispose()
    assert usage_counts == {tenant_a: 3, tenant_b: 1}
