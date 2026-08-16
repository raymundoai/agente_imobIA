from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse
from app.modules.messaging.processor import MessageJobProcessor
from tests.conftest import TEST_WEBHOOK_SECRET

pytestmark = pytest.mark.integration


class FakeAutoReplyAi(AiProviderPort):
    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        return AiProviderResponse(
            text="Olá! Para começar, você busca comprar ou alugar?",
            model="gpt-5.4-mini",
            tokens_used=10,
            input_tokens=6,
            output_tokens=4,
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
    headers = {"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET}

    first = client.post("/webhooks/whatsapp/tenant-a", headers=headers, json=_payload())
    duplicate = client.post("/webhooks/whatsapp/tenant-a", headers=headers, json=_payload())

    assert first.status_code == 200, first.text
    assert first.json()["status"] == "processed"
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["message_id"] == first.json()["message_id"]

    conversations = client.get("/conversations", headers={"Authorization": f"Bearer {token}"})
    assert conversations.status_code == 200
    assert len(conversations.json()) == 1
    contacts = client.get("/contacts", headers={"Authorization": f"Bearer {token}"})
    assert contacts.status_code == 200
    assert len(contacts.json()) == 1
    assert contacts.json()[0]["phone"] == "5511999999999"
    assert conversations.json()[0]["contact_id"] == contacts.json()[0]["id"]
    patch = client.patch(
        f"/contacts/{contacts.json()[0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={**contacts.json()[0], "phone": "5511888888888"},
    )
    assert patch.status_code == 409

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


def test_from_me_message_is_mirrored_without_contact_usage_or_ai_job(
    client: TestClient, migrated_database: str
) -> None:
    tenant, token = _provision(client, "tenant-a")
    client.app.state.container.settings.ai_auto_reply_enabled = True
    payload = _payload("from-phone-1")
    payload["data"]["key"]["fromMe"] = True
    payload["data"]["message"] = {"conversation": "Mensagem enviada pelo celular"}

    response = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=payload,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "mirrored_outbound"
    assert response.json()["job_id"] is None
    detail = client.get(
        f"/conversations/{response.json()['conversation_id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert detail["messages"][0]["direction"] == "outbound"
    assert detail["messages"][0]["author_type"] == "human"
    assert client.get("/contacts", headers={"Authorization": f"Bearer {token}"}).json() == []

    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        usage_count = connection.scalar(
            text("SELECT count(*) FROM usage_records WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant["id"]},
        )
        job_count = connection.scalar(
            text("SELECT count(*) FROM message_jobs WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant["id"]},
        )
    engine.dispose()
    assert (usage_count, job_count) == (0, 0)


def test_group_message_creates_human_conversation_without_lead_or_ai_job(
    client: TestClient,
) -> None:
    _, token = _provision(client, "tenant-a")
    client.app.state.container.settings.ai_auto_reply_enabled = True
    response = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json={
            "event": "messages.upsert",
            "data": {
                "key": {
                    "id": "group-message-1",
                    "remoteJid": "120363419697103562@g.us",
                    "participant": "5511888888888@s.whatsapp.net",
                    "fromMe": False,
                },
                "pushName": "Corretora Ana",
                "groupName": "Captações Zona Sul",
                "message": {"conversation": "Novo imóvel disponível"},
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "processed"
    assert response.json()["job_id"] is None
    auth = {"Authorization": f"Bearer {token}"}
    detail = client.get(f"/conversations/{response.json()['conversation_id']}", headers=auth).json()
    assert detail["is_group"] is True
    assert detail["group_name"] == "Captações Zona Sul"
    assert detail["mode"] == "human"
    assert detail["messages"][0]["sender_name"] == "Corretora Ana"
    assert client.get("/contacts", headers=auth).json() == []


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
    assert response.json()["job_id"] is not None
    processed = MessageJobProcessor(client.app.state.container, "test-worker").process_next()
    assert processed is not None
    assert processed["status"] == "sent"
    assert processed["response_text"] == "Olá! Para começar, você busca comprar ou alugar?"
    detail = client.get(
        f"/conversations/{response.json()['conversation_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert [message["author_type"] for message in detail.json()["messages"]] == [
        "customer",
        "ai",
    ]
    usage = client.get("/usage/commercial", headers={"Authorization": f"Bearer {token}"}).json()
    attendance = next(item for item in usage["resources"] if item["resource"] == "ai_attendance")
    assert attendance["reserved"] == 0
    assert attendance["measured"] == 0


def test_failed_async_reply_is_visible_and_can_be_retried(client: TestClient) -> None:
    _, token = _provision(client, "tenant-a")
    client.app.state.container.settings.ai_auto_reply_enabled = True
    client.app.state.container.ai_provider = None

    webhook = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=_payload("async-failure-1"),
    )
    assert webhook.status_code == 200
    job_id = webhook.json()["job_id"]

    processed = MessageJobProcessor(client.app.state.container, "test-worker").process_next()
    assert processed is not None
    assert processed["status"] == "retrying"
    jobs = client.get(
        "/message-jobs?status=retrying",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert jobs.json()[0]["id"] == job_id
    assert "OpenAI" in jobs.json()[0]["last_error"]

    retried = client.post(
        f"/message-jobs/{job_id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert retried.status_code == 200
    assert retried.json()["attempts"] == 0


def test_duplicate_webhook_creates_only_one_async_job(client: TestClient) -> None:
    _, token = _provision(client, "tenant-a")
    client.app.state.container.settings.ai_auto_reply_enabled = True
    headers = {"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET}

    first = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers=headers,
        json=_payload("async-idempotent-1"),
    )
    duplicate = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers=headers,
        json=_payload("async-idempotent-1"),
    )

    assert first.json()["job_id"] is not None
    assert duplicate.json()["status"] == "duplicate"
    jobs = client.get(
        "/message-jobs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(jobs.json()) == 1


def test_inactive_lead_agent_does_not_enqueue_reply(
    client: TestClient, migrated_database: str
) -> None:
    tenant, token = _provision(client, "tenant-a")
    client.app.state.container.settings.ai_auto_reply_enabled = True
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE tenants SET settings = "
                """'{"agents":{"leads":{"status":"inactive"}}}'::jsonb """
                "WHERE id = :tenant_id"
            ),
            {"tenant_id": tenant["id"]},
        )
    engine.dispose()

    webhook = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=_payload("inactive-agent-1"),
    )
    assert webhook.status_code == 200
    assert webhook.json()["job_id"] is None
    jobs = client.get(
        "/message-jobs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert jobs.json() == []


def test_connected_tenant_owner_is_not_registered_as_lead(
    client: TestClient, migrated_database: str
) -> None:
    tenant, token = _provision(client, "tenant-a")
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE tenants SET settings = "
                """'{"integrations":{"evolution":{"connected_phone":"551199999999"}}}'::jsonb """
                "WHERE id = :tenant_id"
            ),
            {"tenant_id": tenant["id"]},
        )
    engine.dispose()

    webhook = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=_payload("owner-message-1"),
    )

    assert webhook.status_code == 200
    assert webhook.json()["status"] == "ignored_tenant_owner"
    assert client.get("/contacts", headers={"Authorization": f"Bearer {token}"}).json() == []
    assert client.get("/conversations", headers={"Authorization": f"Bearer {token}"}).json() == []
