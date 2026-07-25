import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _provision(client: TestClient, slug: str, email: str) -> str:
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
    return login.json()["access_token"]


def test_maintenance_tickets_are_tenant_isolated_via_api(client: TestClient) -> None:
    token_a = _provision(client, "tenant-a", "admin-a@example.com")
    token_b = _provision(client, "tenant-b", "admin-b@example.com")
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}

    created = client.post(
        "/maintenance/tickets",
        headers=auth_a,
        json={
            "customer_name": "Ana",
            "phone": "5511999999999",
            "property_reference": "Apto 12",
            "issue_type": "vazamento",
            "description": "Vazamento na cozinha",
            "urgency": "high",
            "attachments": [],
        },
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]

    assert client.get(f"/maintenance/tickets/{ticket_id}", headers=auth_b).status_code == 404
    assert (
        client.patch(
            f"/maintenance/tickets/{ticket_id}",
            headers=auth_b,
            json={"status": "in_progress"},
        ).status_code
        == 404
    )
    tickets_b = client.get("/maintenance/tickets", headers=auth_b)
    assert tickets_b.status_code == 200
    assert tickets_b.json() == []

    updated = client.patch(
        f"/maintenance/tickets/{ticket_id}",
        headers=auth_a,
        json={"status": "in_progress"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "in_progress"
