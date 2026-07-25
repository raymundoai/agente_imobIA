import pytest
from fastapi.testclient import TestClient

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
    assert response.status_code == 201, response.text
    login = client.post(
        "/auth/login",
        json={"tenant_slug": "tenant-a", "email": "admin@example.com", "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_capture_deduplicates_and_exposes_mission(client: TestClient) -> None:
    token = _provision(client)
    auth = {"Authorization": f"Bearer {token}"}
    demand = client.post(
        "/leads/demands",
        headers=auth,
        json={
            "lead_name": "Maria",
            "phone": "5511999999999",
            "purpose": "buy",
            "property_type": "apartamento",
            "city": "São Paulo",
            "neighborhoods": ["Pinheiros"],
            "price_min": "500000",
            "price_max": "900000",
            "bedrooms": 2,
        },
    )
    assert demand.status_code == 201, demand.text
    demand_id = demand.json()["id"]

    payload = {
        "demand_id": demand_id,
        "source": "portal",
        "source_url": "https://portal.test/imovel-duplicado",
        "title": "Apartamento em Pinheiros",
        "city": "São Paulo",
        "neighborhood": "Pinheiros",
        "price": "800000",
        "purpose": "buy",
        "property_type": "apartamento",
        "bedrooms": 2,
    }
    first = client.post("/capture/properties", headers=auth, json=payload)
    second = client.post(
        "/capture/properties", headers=auth, json={**payload, "title": "Novo título"}
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["title"] == "Novo título"

    linked = client.get(f"/properties?demand_id={demand_id}", headers=auth)
    assert linked.status_code == 200, linked.text
    assert len(linked.json()) == 1

    mission = client.get(f"/capture/missions/{demand_id}", headers=auth)
    assert mission.status_code == 200, mission.text
    assert mission.json()["search_filters"]["city"] == "São Paulo"
    assert mission.json()["existing_matches"][0]["id"] == first.json()["id"]
