from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse
from tests.conftest import TEST_WEBHOOK_SECRET

pytestmark = pytest.mark.integration


class FakeAiProvider(AiProviderPort):
    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        return AiProviderResponse(
            text="Resposta IA tenant-scoped",
            model="fake-model",
            tokens_used=42,
            detected_intent="duvida_faq",
        )


def _provision(client: TestClient, slug: str, email: str) -> tuple[str, str]:
    password = "valid-test-password-123"
    response = client.post(
        "/tenants",
        json={
            "name": slug,
            "slug": slug,
            "admin_name": "Admin",
            "admin_email": email,
            "admin_password": password,
        },
    )
    assert response.status_code == 201, response.text
    login = client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return response.json()["id"], login.json()["access_token"]


def _receive(client: TestClient, slug: str, message_id: str) -> dict[str, Any]:
    response = client.post(
        f"/webhooks/whatsapp/{slug}",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json={
            "event": "MESSAGES_UPSERT",
            "data": {
                "key": {
                    "id": message_id,
                    "remoteJid": "5511888888888@s.whatsapp.net",
                    "fromMe": False,
                },
                "message": {"conversation": "Olá"},
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_ai_reply_records_audit_log_inside_tenant_scope(
    client: TestClient, migrated_database: str
) -> None:
    client.app.state.container.ai_provider = FakeAiProvider()
    tenant_a, token_a = _provision(client, "tenant-a", "admin-a@example.com")
    tenant_b, token_b = _provision(client, "tenant-b", "admin-b@example.com")
    conversation_a = _receive(client, "tenant-a", "msg-a")["conversation_id"]
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}

    assert (
        client.post(
            f"/ai/conversations/{conversation_a}/respond",
            headers=auth_b,
            json={"send_to_channel": False},
        ).status_code
        == 404
    )

    response = client.post(
        f"/ai/conversations/{conversation_a}/respond",
        headers=auth_a,
        json={"send_to_channel": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["detected_intent"] == "duvida_faq"

    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        audit_counts = dict(
            connection.execute(
                text(
                    "SELECT tenant_id::text, count(*) FROM ai_audit_logs "
                    "WHERE tenant_id IN (:tenant_a, :tenant_b) GROUP BY tenant_id"
                ),
                {"tenant_a": tenant_a, "tenant_b": tenant_b},
            ).all()
        )
        usage_count = connection.scalar(
            text(
                "SELECT count(*) FROM usage_records "
                "WHERE tenant_id = :tenant_id AND type = 'ai_call'"
            ),
            {"tenant_id": tenant_a},
        )
    engine.dispose()
    assert audit_counts == {tenant_a: 1}
    assert usage_count == 1
