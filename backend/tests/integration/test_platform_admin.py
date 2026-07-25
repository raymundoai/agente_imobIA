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
    dashboard = client.get("/platform/dashboard", headers=auth)
    assert dashboard.status_code == 200
    assert dashboard.json()["active_clients"] == 1
    assert dashboard.json()["total_users"] == 1

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
