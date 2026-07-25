import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_WEBHOOK_SECRET

pytestmark = pytest.mark.integration


def _provision(client: TestClient) -> str:
    password = "valid-test-password-123"
    response = client.post(
        "/tenants",
        json={
            "name": "Tenant A",
            "slug": "tenant-a",
            "admin_name": "Admin",
            "admin_email": "admin@example.com",
            "admin_password": password,
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/auth/login",
        json={"tenant_slug": "tenant-a", "email": "admin@example.com", "password": password},
    )
    return login.json()["access_token"]


def _update(message_id: int = 100) -> dict[str, object]:
    return {
        "update_id": 500,
        "message": {
            "message_id": message_id,
            "from": {"id": 321, "first_name": "Cliente Telegram"},
            "chat": {"id": 321, "type": "private"},
            "text": "Quero comprar um apartamento",
        },
    }


def test_telegram_webhook_is_secure_idempotent_and_visible_in_chat(client: TestClient) -> None:
    token = _provision(client)
    invalid = client.post(
        "/webhooks/telegram/tenant-a",
        headers={"X-Telegram-Bot-Api-Secret-Token": "invalid"},
        json=_update(),
    )
    assert invalid.status_code == 401

    headers = {"X-Telegram-Bot-Api-Secret-Token": TEST_WEBHOOK_SECRET}
    first = client.post("/webhooks/telegram/tenant-a", headers=headers, json=_update())
    duplicate = client.post("/webhooks/telegram/tenant-a", headers=headers, json=_update())
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "processed"
    assert duplicate.json()["status"] == "duplicate"

    conversations = client.get(
        "/conversations", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert conversations[0]["channel"] == "telegram"
    detail = client.get(
        f"/conversations/{conversations[0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert detail["messages"][0]["text"] == "Quero comprar um apartamento"
