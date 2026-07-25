import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _provision(client: TestClient, slug: str, email: str) -> str:
    password = "valid-test-password-123"
    created = client.post(
        "/tenants",
        json={
            "name": slug,
            "slug": slug,
            "admin_name": "Admin",
            "admin_email": email,
            "admin_password": password,
        },
    )
    assert created.status_code == 201
    login = client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": email, "password": password},
    )
    return login.json()["access_token"]


def test_manual_property_and_contacts_are_persisted_and_tenant_isolated(
    client: TestClient,
) -> None:
    token_a = _provision(client, "tenant-a", "a@example.com")
    token_b = _provision(client, "tenant-b", "b@example.com")
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}

    property_response = client.post(
        "/properties",
        headers=auth_a,
        json={
            "title": "Casa sobrado com 3 quartos",
            "listing_code": "125931",
            "purpose": "both",
            "property_type": "sobrado",
            "category": "residential",
            "sale_price": 3500000,
            "rent_price": 18000,
            "description": "Imóvel completo no Jardim América.",
            "bedrooms": 3,
            "suites": 3,
            "bathrooms": 3,
            "parking_spaces": 10,
            "area": 850,
            "land_area": 1120,
            "address": {
                "street": "Rua Argentina",
                "neighborhood": "Jardins",
                "city": "São Paulo",
                "state": "SP",
            },
            "details": {
                "pet_friendly": True,
                "rooms": ["Sala com lareira", "Área de serviço"],
                "amenities": ["Piscina", "Churrasqueira", "Sauna"],
            },
        },
    )
    assert property_response.status_code == 201, property_response.text
    assert property_response.json()["details"]["amenities"] == [
        "Piscina",
        "Churrasqueira",
        "Sauna",
    ]
    assert len(client.get("/properties", headers=auth_a).json()) == 1
    assert client.get("/properties", headers=auth_b).json() == []

    contact = client.post(
        "/contacts",
        headers=auth_a,
        json={
            "name": "Maria Proprietária",
            "phone": "5511999999999",
            "email": "maria@example.com",
            "kind": "owner",
            "tags": ["Proprietária", "Jardins"],
            "interest": "Administração do imóvel",
            "notes": "Contato principal",
        },
    )
    assert contact.status_code == 201, contact.text
    assert len(client.get("/contacts", headers=auth_a).json()) == 1
    assert client.get("/contacts", headers=auth_b).json() == []


def test_property_requires_prices_for_each_selected_offer(client: TestClient) -> None:
    token = _provision(client, "tenant-a", "a@example.com")
    response = client.post(
        "/properties",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Apartamento para venda e aluguel",
            "purpose": "both",
            "property_type": "apartamento",
            "category": "residential",
            "sale_price": 900000,
            "address": {
                "street": "Rua Teste",
                "neighborhood": "Centro",
                "city": "São Paulo",
                "state": "SP",
            },
        },
    )
    assert response.status_code == 422


def test_property_image_upload_validates_and_serves_file(client: TestClient) -> None:
    token = _provision(client, "tenant-a", "a@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/properties",
        headers=auth,
        json={
            "title": "Apartamento de teste",
            "purpose": "buy",
            "property_type": "apartamento",
            "category": "residential",
            "sale_price": 500000,
            "address": {
                "street": "Rua Teste",
                "neighborhood": "Centro",
                "city": "São Paulo",
                "state": "SP",
            },
        },
    )
    property_id = created.json()["id"]
    png = b"\x89PNG\r\n\x1a\nminimal-test-content"
    response = client.post(
        f"/properties/{property_id}/images",
        headers=auth,
        files=[("files", ("fachada.png", png, "image/png"))],
    )

    assert response.status_code == 201, response.text
    image = response.json()[0]
    served = client.get(image["display_url"], headers=auth)
    assert served.status_code == 200
    assert served.content == png
    assert client.get(image["display_url"]).status_code == 401
    other_token = _provision(client, "tenant-b", "b@example.com")
    assert (
        client.get(
            image["display_url"],
            headers={"Authorization": f"Bearer {other_token}"},
        ).status_code
        == 404
    )


def test_property_image_treatment_requires_configured_openai(client: TestClient) -> None:
    token = _provision(client, "tenant-a", "a@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/properties",
        headers=auth,
        json={
            "title": "Apartamento de teste",
            "purpose": "buy",
            "property_type": "apartamento",
            "category": "residential",
            "sale_price": 500000,
            "address": {
                "street": "Rua Teste",
                "neighborhood": "Centro",
                "city": "São Paulo",
                "state": "SP",
            },
        },
    )
    property_id = created.json()["id"]
    upload = client.post(
        f"/properties/{property_id}/images",
        headers=auth,
        files=[
            (
                "files",
                ("fachada.png", b"\x89PNG\r\n\x1a\nminimal-test-content", "image/png"),
            )
        ],
    )
    image_id = upload.json()[0]["id"]
    response = client.post(
        f"/properties/{property_id}/images/{image_id}/reprocess",
        headers=auth,
        json={"optimizations": ["corrigir iluminação"]},
    )

    assert response.status_code == 503
    assert "OpenAI" in response.json()["detail"]
