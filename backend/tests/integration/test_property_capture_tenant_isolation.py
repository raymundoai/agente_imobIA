import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


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


def test_captured_properties_are_tenant_isolated(client: TestClient) -> None:
    _, token_a = _provision(client, "tenant-a", "admin-a@example.com")
    _, token_b = _provision(client, "tenant-b", "admin-b@example.com")
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}

    payload = {
        "source": "portal",
        "source_url": "https://portal.test/imovel-1",
        "title": "Apartamento",
        "city": "São Paulo",
        "price": "700000",
        "purpose": "buy",
        "property_type": "apartamento",
    }
    assert client.post("/capture/properties", headers=auth_a, json=payload).status_code == 201
    assert client.post("/capture/properties", headers=auth_b, json=payload).status_code == 201

    props_a = client.get("/properties", headers=auth_a)
    props_b = client.get("/properties", headers=auth_b)
    assert props_a.status_code == 200
    assert props_b.status_code == 200
    assert len(props_a.json()) == 1
    assert len(props_b.json()) == 1
    assert props_a.json()[0]["tenant_id"] != props_b.json()[0]["tenant_id"]
