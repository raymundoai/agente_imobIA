import pytest
from fastapi.testclient import TestClient

from tests.integration.test_asaas_billing import _platform_token
from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration


def test_platform_team_gives_a_forgotten_admin_a_new_password_link(client: TestClient) -> None:
    tenant, token = _provision(client, "senha-esquecida")
    platform = {"Authorization": f"Bearer {_platform_token(client)}"}
    client.app.state.container.settings.app_public_url = "https://app.immobia.example.com"

    users = client.get(f"/platform/tenants/{tenant['id']}/users", headers=platform).json()
    admin = next(user for user in users if user["is_master"])

    generated = client.post(
        f"/platform/tenants/{tenant['id']}/users/{admin['id']}/password-link", headers=platform
    )
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["link"].startswith("https://app.immobia.example.com/aceitar-convite?token=")

    accepted = client.post(
        "/auth/accept-invitation",
        json={"token": body["token"], "password": "nova-senha-bem-forte-123"},
    )
    assert accepted.status_code == 200, accepted.text
    old = client.post(
        "/auth/login",
        json={
            "tenant_slug": tenant["slug"],
            "email": "admin@example.com",
            "password": "valid-test-password-123",
        },
    )
    assert old.status_code == 401
    new = client.post(
        "/auth/login",
        json={
            "tenant_slug": tenant["slug"],
            "email": "admin@example.com",
            "password": "nova-senha-bem-forte-123",
        },
    )
    assert new.status_code == 200, new.text

    history = client.get(
        "/activity", headers={"Authorization": f"Bearer {new.json()['access_token']}"}
    ).json()
    assert history[0]["action"] == "password_link"
    assert history[0]["actor_type"] == "system"

    tenant_token = {"Authorization": f"Bearer {token}"}
    assert (
        client.get(f"/platform/tenants/{tenant['id']}/users", headers=tenant_token).status_code
        == 401
    )
