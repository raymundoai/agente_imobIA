import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_PLATFORM_BOOTSTRAP_TOKEN

pytestmark = pytest.mark.integration


def _bootstrap(client: TestClient) -> str:
    response = client.post(
        "/platform/auth/bootstrap",
        headers={"X-Platform-Bootstrap-Token": TEST_PLATFORM_BOOTSTRAP_TOKEN},
        json={
            "name": "Dono da Plataforma",
            "email": "platform@example.com",
            "password": "strong-platform-password-123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def test_platform_admin_can_manage_tenants_and_read_global_dashboard(
    client: TestClient,
) -> None:
    token = _bootstrap(client)
    auth = {"Authorization": f"Bearer {token}"}
    second_bootstrap = client.post(
        "/platform/auth/bootstrap",
        headers={"X-Platform-Bootstrap-Token": TEST_PLATFORM_BOOTSTRAP_TOKEN},
        json={
            "name": "Outro",
            "email": "other@example.com",
            "password": "another-platform-password-123",
        },
    )
    assert second_bootstrap.status_code == 401

    created = client.post(
        "/platform/tenants",
        headers=auth,
        json={
            "name": "Imobiliária Piloto",
            "slug": "piloto",
            "admin_name": "Admin Piloto",
            "admin_email": "admin@piloto.com",
            "admin_password": "tenant-admin-password-123",
        },
    )
    assert created.status_code == 201, created.text
    tenant_id = created.json()["id"]
    assert created.json()["credit_balance"] == 0
    grant = client.post(
        f"/platform/tenants/{tenant_id}/credits/grants",
        headers=auth,
        json={
            "credits": 10000,
            "description": "Créditos do piloto",
            "idempotency_key": "pilot-initial-grant",
        },
    )
    assert grant.status_code == 201, grant.text
    assert grant.json()["balance_after"] == 10000
    repeated = client.post(
        f"/platform/tenants/{tenant_id}/credits/grants",
        headers=auth,
        json={
            "credits": 10000,
            "description": "Créditos do piloto",
            "idempotency_key": "pilot-initial-grant",
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == grant.json()["id"]
    policy = client.patch(
        f"/platform/tenants/{tenant_id}/credits/settings",
        headers=auth,
        json={"enforcement_mode": "enforce", "unlimited_messages": True},
    )
    assert policy.status_code == 200
    assert policy.json()["credit_balance"] == 10000
    assert policy.json()["credit_enforcement"] == "enforce"
    assert policy.json()["unlimited_messages"] is True
    ledger = client.get(f"/platform/tenants/{tenant_id}/credits/ledger", headers=auth)
    assert ledger.status_code == 200
    assert len(ledger.json()) == 1
    dashboard = client.get("/platform/dashboard", headers=auth)
    assert dashboard.status_code == 200
    assert dashboard.json()["active_clients"] == 1
    assert dashboard.json()["total_users"] == 1
    assert dashboard.json()["credits_outstanding"] == 10000

    suspended = client.patch(
        f"/platform/tenants/{tenant_id}/status",
        headers=auth,
        json={"status": "inactive"},
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "inactive"
    assert client.get("/platform/tenants", headers=auth).json()[0]["name"] == "Imobiliária Piloto"


def test_tenant_token_cannot_access_platform_routes(client: TestClient) -> None:
    created = client.post(
        "/tenants",
        json={
            "name": "Tenant",
            "slug": "tenant-a",
            "admin_name": "Admin",
            "admin_email": "admin@example.com",
            "admin_password": "tenant-admin-password-123",
        },
    )
    assert created.status_code == 201
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "tenant-a",
            "email": "admin@example.com",
            "password": "tenant-admin-password-123",
        },
    )
    response = client.get(
        "/platform/dashboard",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 401
