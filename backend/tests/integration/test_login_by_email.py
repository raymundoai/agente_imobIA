import pytest
from fastapi.testclient import TestClient

from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration

PASSWORD = "valid-test-password-123"


def _login(client: TestClient, **payload: str):
    return client.post("/auth/login", json={"email": "admin@example.com", **payload})


def test_login_finds_the_company_by_email(client: TestClient) -> None:
    _provision(client, "tenant-a")

    response = _login(client, password=PASSWORD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant_slug"] == "tenant-a"
    assert body["access_token"]
    assert body["companies"] == []

    me = client.get("/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == "admin@example.com"


def test_login_without_company_rejects_wrong_password_and_unknown_email(
    client: TestClient,
) -> None:
    _provision(client, "tenant-a")

    assert _login(client, password="wrong-password-123").status_code == 401
    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == "Invalid credentials"


def test_same_email_in_two_companies_asks_which_one(client: TestClient) -> None:
    _provision(client, "tenant-a")
    _provision(client, "tenant-b")

    choice = _login(client, password=PASSWORD)
    assert choice.status_code == 200, choice.text
    body = choice.json()
    assert body["access_token"] is None
    assert sorted(item["slug"] for item in body["companies"]) == ["tenant-a", "tenant-b"]

    chosen = _login(client, password=PASSWORD, tenant_slug="tenant-b")
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["tenant_slug"] == "tenant-b"

    # The company list is only revealed after the password matches.
    assert _login(client, password="wrong-password-123").status_code == 401
