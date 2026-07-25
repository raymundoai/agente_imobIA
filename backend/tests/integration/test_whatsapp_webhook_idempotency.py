from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse
from tests.conftest import TEST_WEBHOOK_SECRET

pytestmark = pytest.mark.integration


class FakeAutoReplyAi(AiProviderPort):
    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        return AiProviderResponse(
            text="Olá! Para começar, você busca comprar ou alugar?",
            model="fake-auto-reply",
            tokens_used=10,
            detected_intent="qualificacao_lead",
        )


def _provision(client: TestClient, slug: str) -> tuple[dict[str, Any], str]:
    password = "valid-test-password-123"
    response = client.post(
        "/tenants",
        json={
            "name": f"Tenant {slug}",
            "slug": slug,
            "admin_name": "Admin",
            "admin_email": "admin@example.com",
            "admin_password": password,
        },
    )
    assert response.status_code == 201, response.text
    login = client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": "admin@example.com", "password": password},
    )
    assert login.status_code == 200, login.text
    return response.json(), login.json()["access_token"]


def _payload(external_id: str = "wa-message-1") -> dict[str, Any]:
    return {
        "event": "messages.upsert",
        "instance": "tenant-a",
        "data": {
            "key": {
                "id": external_id,
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Cliente Teste",
            "message": {"conversation": "Procuro apartamento em São Paulo"},
        },
    }


def test_webhook_is_idempotent_for_message_and_usage(
    client: TestClient, migrated_database: str
) -> None:
    tenant, token = _provision(client, "tenant-a")
    params = {"token": TEST_WEBHOOK_SECRET}

    first = client.post("/webhooks/whatsapp/tenant-a", params=params, json=_payload())
    duplicate = client.post("/webhooks/whatsapp/tenant-a", params=params, json=_payload())

    assert first.status_code == 200, first.text
    assert first.json()["status"] == "processed"
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["message_id"] == first.json()["message_id"]

    conversations = client.get("/conversations", headers={"Authorization": f"Bearer {token}"})
    assert conversations.status_code == 200
    assert len(conversations.json()) == 1

    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        counts = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM messages WHERE tenant_id = :tenant_id), "
                "(SELECT count(*) FROM usage_records WHERE tenant_id = :tenant_id)"
            ),
            {"tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert counts == (1, 1)


def test_webhook_rejects_invalid_secret_without_persisting(client: TestClient) -> None:
    _, token = _provision(client, "tenant-a")

    response = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": "invalid"},
        json=_payload(),
    )

    assert response.status_code == 401
    conversations = client.get("/conversations", headers={"Authorization": f"Bearer {token}"})
    assert conversations.json() == []


def test_webhook_can_generate_local_ai_reply_without_sending_to_whatsapp(
    client: TestClient,
) -> None:
    _, token = _provision(client, "tenant-a")
    client.app.state.container.ai_provider = FakeAutoReplyAi()
    client.app.state.container.settings.ai_auto_reply_enabled = True
    client.app.state.container.settings.ai_auto_send_to_channel = False

    response = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=_payload("auto-reply-1"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["ai_response"] == "Olá! Para começar, você busca comprar ou alugar?"
    detail = client.get(
        f"/conversations/{response.json()['conversation_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert [message["author_type"] for message in detail.json()["messages"]] == [
        "customer",
        "ai",
    ]
