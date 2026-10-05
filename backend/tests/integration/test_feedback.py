import pytest
from fastapi.testclient import TestClient

from tests.integration.test_asaas_billing import _platform_token
from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration


def test_feedback_reaches_the_platform_team_with_account_details(client: TestClient) -> None:
    tenant, token = _provision(client, "feedback-beta")
    auth = {"Authorization": f"Bearer {token}"}
    sent = client.post(
        "/feedback",
        headers={**auth, "User-Agent": "Teste/1.0"},
        json={
            "kind": "problem",
            "message": "O QR Code some antes de eu conseguir ler.",
            "page": "/configuracoes?aba=channels",
            "contact_phone": "(51) 99999-0000",
        },
    )
    assert sent.status_code == 201, sent.text

    platform = {"Authorization": f"Bearer {_platform_token(client)}"}
    items = client.get("/platform/feedback?status=new", headers=platform).json()
    assert len(items) == 1
    item = items[0]
    assert item["tenant_name"] == "Tenant feedback-beta"
    assert item["user_email"] == "admin@example.com"
    assert item["page"] == "/configuracoes?aba=channels"
    assert item["user_agent"] == "Teste/1.0"

    resolved = client.patch(
        f"/platform/feedback/{item['id']}",
        headers=platform,
        json={"status": "resolved", "admin_note": "Corrigido na versão de hoje."},
    ).json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None
    assert client.get("/platform/feedback?status=new", headers=platform).json() == []

    assert client.get("/platform/feedback", headers=auth).status_code == 401
    assert (
        client.post("/feedback", json={"kind": "problem", "message": "sem login"}).status_code
        == 401
    )
