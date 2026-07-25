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

    def receive_message(self, payload: dict[str, Any]) -> InboundChannelMessage:
        return self._delegate.receive_message(payload)

    def send_message(
        self, credentials: ChannelCredentials, phone: str, text: str
    ) -> SentChannelMessage:
        self.sent.append((phone, text))
        return SentChannelMessage(external_message_id=f"sent-{len(self.sent)}")


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


def _receive(client: TestClient, slug: str) -> dict[str, Any]:
    response = client.post(
        f"/webhooks/whatsapp/{slug}",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json={
            "event": "MESSAGES_UPSERT",
            "data": {
                "key": {
                    "id": "same-external-id",
                    "remoteJid": "5511888888888@s.whatsapp.net",
                    "fromMe": False,
                },
                "message": {"conversation": "Olá"},
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


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
    assert usage_counts == {tenant_a: 2, tenant_b: 1}
