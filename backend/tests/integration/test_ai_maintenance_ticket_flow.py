from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse, AiToolCall
from tests.conftest import TEST_WEBHOOK_SECRET

pytestmark = pytest.mark.integration


class FakeAiProvider(AiProviderPort):
    def __init__(self) -> None:
        self.calls = 0

    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return AiProviderResponse(
                text="",
                model="fake-model",
                tokens_used=7,
                tool_calls=[
                    AiToolCall(
                        name="create_maintenance_ticket",
                        arguments={
                            "customer_name": "Carlos",
                            "phone": "5511888888888",
                            "property_reference": "Casa 2",
                            "issue_type": "sem energia",
                            "description": "Imóvel está sem energia",
                            "urgency": "high",
                            "attachments": [],
                        },
                    )
                ],
            )
        return AiProviderResponse(
            text="Abri o chamado de manutenção.", model="fake-model", tokens_used=9
        )


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


def _receive(client: TestClient, slug: str, text_value: str, message_id: str) -> dict[str, Any]:
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
                "message": {"conversation": text_value},
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_ai_creates_maintenance_ticket_and_guardrail_handoff(
    client: TestClient, migrated_database: str
) -> None:
    client.app.state.container.ai_provider = FakeAiProvider()
    tenant_id, token = _provision(client, "tenant-a")
    conversation_id = _receive(client, "tenant-a", "Estou sem energia no imóvel", "m-1")[
        "conversation_id"
    ]

    response = client.post(
        f"/ai/conversations/{conversation_id}/respond",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_to_channel": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["tools_called"][0]["name"] == "create_maintenance_ticket"

    guarded_conversation_id = _receive(
        client,
        "tenant-a",
        "Quero negociar desconto e cancelar contrato",
        "m-2",
    )["conversation_id"]
    guarded = client.post(
        f"/ai/conversations/{guarded_conversation_id}/respond",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_to_channel": False},
    )
    assert guarded.status_code == 200, guarded.text
    assert guarded.json()["model"] == "guardrail"
    assert guarded.json()["handoff_reason"] == "financial_negotiation"

    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        ticket_count = connection.scalar(
            text("SELECT count(*) FROM maintenance_tickets WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        guardrail_audit_count = connection.scalar(
            text(
                "SELECT count(*) FROM ai_audit_logs "
                "WHERE tenant_id = :tenant_id AND model = 'guardrail'"
            ),
            {"tenant_id": tenant_id},
        )
    engine.dispose()
    assert ticket_count == 1
    assert guardrail_audit_count == 1
