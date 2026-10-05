import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from tests.integration.test_asaas_billing import _platform_token
from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration

PASSWORD = "valid-test-password-123"


def _login(client: TestClient, password: str = PASSWORD, email: str = "admin@example.com"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_suspending_an_agency_cuts_open_sessions_and_refresh(client: TestClient) -> None:
    tenant, _ = _provision(client, "tenant-a")
    session = _login(client).json()
    auth = {"Authorization": f"Bearer {session['access_token']}"}
    assert client.get("/users/me", headers=auth).status_code == 200

    platform = {"Authorization": f"Bearer {_platform_token(client)}"}
    suspended = client.patch(
        f"/platform/tenants/{tenant['id']}/status", headers=platform, json={"status": "inactive"}
    )
    assert suspended.status_code == 200, suspended.text

    assert client.get("/users/me", headers=auth).status_code == 401
    refresh = client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert refresh.status_code == 401

    client.patch(
        f"/platform/tenants/{tenant['id']}/status", headers=platform, json={"status": "active"}
    )
    assert client.get("/users/me", headers=auth).status_code == 200


def test_development_routes_are_closed_by_default() -> None:
    assert Settings.model_fields["app_env"].default == "production"


def test_dev_tenant_route_refused_outside_development(client: TestClient) -> None:
    client.app.state.container.settings.app_env = "production"
    response = client.post(
        "/tenants",
        json={
            "name": "Intrusa",
            "slug": "intrusa",
            "admin_name": "Admin",
            "admin_email": "x@example.com",
            "admin_password": PASSWORD,
        },
    )
    assert response.status_code == 403


def test_account_is_locked_after_repeated_wrong_passwords(client: TestClient) -> None:
    _provision(client, "tenant-a")
    for _ in range(10):
        assert _login(client, "wrong-password-123").status_code == 401

    blocked = _login(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.json()["error"] == "too_many_requests"
    # The lock is per account: another email from the same address still gets an answer.
    assert _login(client, email="someone-else@example.com").status_code == 401


def test_successful_logins_do_not_consume_the_account_limit(client: TestClient) -> None:
    _provision(client, "tenant-a")
    for _ in range(12):
        assert _login(client).status_code == 200


def test_address_limit_stops_password_spraying(client: TestClient) -> None:
    for index in range(30):
        assert _login(client, email=f"user{index}@example.com").status_code == 401
    assert _login(client, email="another@example.com").status_code == 429


def test_platform_login_is_limited(client: TestClient) -> None:
    _platform_token(client)
    for _ in range(5):
        response = client.post(
            "/platform/auth/login",
            json={"email": "billing@example.com", "password": "wrong-password-123"},
        )
        assert response.status_code == 401
    blocked = client.post(
        "/platform/auth/login",
        json={"email": "billing@example.com", "password": "strong-platform-password-123"},
    )
    assert blocked.status_code == 429


def test_signup_is_limited_per_address(client: TestClient) -> None:
    client.app.state.container.settings.public_signup_enabled = True
    for index in range(5):
        response = client.post(
            "/signup",
            json={
                "company_name": f"Imobiliária {index}",
                "admin_name": "Ana",
                "email": f"ana{index}@example.com",
                "password": PASSWORD,
                "accept_terms": True,
            },
        )
        assert response.status_code == 201, response.text
    blocked = client.post(
        "/signup",
        json={
            "company_name": "Imobiliária 6",
            "admin_name": "Ana",
            "email": "ana6@example.com",
            "password": PASSWORD,
            "accept_terms": True,
        },
    )
    assert blocked.status_code == 429
