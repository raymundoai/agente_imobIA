from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.modules.properties.adapters.models import PropertyImageModel
from tests.integration.test_asaas_billing import _platform_token
from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)
MEMBERSHIP = {
    "accept_terms": True,
    "partner_commission_percent": 50,
    "contact_name": "Corretor Responsável",
    "contact_phone": "51999990000",
    "contact_email": "parcerias@example.com",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _paid(client: TestClient, platform: dict[str, str], tenant_id: str) -> None:
    response = client.put(
        f"/platform/tenants/{tenant_id}/commercial-subscription",
        headers=platform,
        json={"plan_code": "ia_essencial", "enforcement_mode": "enforce"},
    )
    assert response.status_code == 200, response.text


def _property(client: TestClient, token: str, **overrides: Any) -> dict[str, Any]:
    payload = {
        "title": "Apartamento 2 dormitórios no Menino Deus",
        "purpose": "buy",
        "property_type": "apartamento",
        "category": "residential",
        "sale_price": "450000",
        "bedrooms": 2,
        "area": 70,
        "address": {
            "street": "Rua Secreta do Proprietário",
            "number": "123",
            "neighborhood": "Menino Deus",
            "city": "Porto Alegre",
            "state": "RS",
        },
        "owner_name": "Dona Proprietária",
        "owner_phone": "51988887777",
        **overrides,
    }
    response = client.post("/properties", headers=_auth(token), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _image(client: TestClient, tenant_id: str, property_id: str) -> UUID:
    container = client.app.state.container
    image_id = uuid4()
    key = f"{tenant_id}/{property_id}/{image_id}/original.png"
    container.property_image_storage.put(UUID(tenant_id), key, PNG, "image/png")
    with container.database.session_factory() as session:
        session.add(
            PropertyImageModel(
                id=image_id,
                tenant_id=UUID(tenant_id),
                property_id=UUID(property_id),
                original_storage_key=key,
                original_name="fachada.png",
                original_content_type="image/png",
                original_size=len(PNG),
                status="ready",
                is_primary=True,
                sort_order=0,
            )
        )
        session.commit()
    return image_id


def _demand(client: TestClient, token: str) -> str:
    response = client.post(
        "/leads/demands",
        headers=_auth(token),
        json={
            "lead_name": "Cliente Comprador",
            "phone": "5511999990000",
            "purpose": "buy",
            "city": "Porto Alegre",
            "state": "RS",
            "price_max": "500000",
            "bedrooms": 2,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def network(client: TestClient) -> dict[str, Any]:
    owner, owner_token = _provision(client, "dona-do-imovel")
    partner, partner_token = _provision(client, "parceira")
    platform = _auth(_platform_token(client))
    return {
        "owner": owner,
        "owner_token": owner_token,
        "partner": partner,
        "partner_token": partner_token,
        "platform": platform,
    }


def _join_and_share(client: TestClient, ctx: dict[str, Any]) -> tuple[dict, UUID]:
    for tenant, token in (
        (ctx["owner"], ctx["owner_token"]),
        (ctx["partner"], ctx["partner_token"]),
    ):
        _paid(client, ctx["platform"], tenant["id"])
        joined = client.put("/network/settings", headers=_auth(token), json=MEMBERSHIP)
        assert joined.status_code == 200, joined.text
    listing = _property(client, ctx["owner_token"])
    image_id = _image(client, ctx["owner"]["id"], listing["id"])
    shared = client.put(
        f"/network/properties/{listing['id']}/share",
        headers=_auth(ctx["owner_token"]),
        json={"shared": True},
    )
    assert shared.status_code == 200, shared.text
    return listing, image_id


def test_network_is_a_paid_plan_feature(client: TestClient, network: dict[str, Any]) -> None:
    token = network["partner_token"]
    settings = client.get("/network/settings", headers=_auth(token)).json()
    assert settings["eligible"] is False
    assert "Rede ImmobIA" in settings["terms_text"]

    joined = client.put("/network/settings", headers=_auth(token), json=MEMBERSHIP)
    assert joined.status_code == 402
    demand_id = _demand(client, token)
    assert (
        client.get(f"/network/search?demand_id={demand_id}", headers=_auth(token)).status_code
        == 402
    )


def test_sharing_requires_terms_photo_and_own_listing(
    client: TestClient, network: dict[str, Any]
) -> None:
    token = network["owner_token"]
    _paid(client, network["platform"], network["owner"]["id"])
    listing = _property(client, token)
    share = lambda: client.put(  # noqa: E731
        f"/network/properties/{listing['id']}/share", headers=_auth(token), json={"shared": True}
    )

    assert "termo" in share().json()["detail"]
    client.put("/network/settings", headers=_auth(token), json=MEMBERSHIP)
    assert "foto" in share().json()["detail"]
    _image(client, network["owner"]["id"], listing["id"])
    assert share().status_code == 200

    detail = client.get(f"/properties/{listing['id']}", headers=_auth(token)).json()
    assert detail["network_shared"] is True


def test_partner_finds_listing_without_owner_data_and_sees_photo(
    client: TestClient, network: dict[str, Any]
) -> None:
    listing, image_id = _join_and_share(client, network)
    partner = _auth(network["partner_token"])
    demand_id = _demand(client, network["partner_token"])

    results = client.get(f"/network/search?demand_id={demand_id}", headers=partner)
    assert results.status_code == 200, results.text
    body = results.json()
    assert [item["id"] for item in body] == [listing["id"]]
    found = body[0]
    assert found["agency_name"] == "Tenant dona-do-imovel"
    assert found["partner_commission_percent"] == 50
    assert found["image_ids"] == [str(image_id)]
    assert found["partnership"] is None
    raw = results.text
    for private in ("Rua Secreta", "Dona Proprietária", "51988887777", "parcerias@example.com"):
        assert private not in raw

    photo = client.get(
        f"/network/properties/{listing['id']}/images/{image_id}/content", headers=partner
    )
    assert photo.status_code == 200
    assert photo.content == PNG

    # The owner does not see its own listing in the network.
    owner_demand = _demand(client, network["owner_token"])
    own = client.get(
        f"/network/search?demand_id={owner_demand}", headers=_auth(network["owner_token"])
    )
    assert own.json() == []


def test_unsharing_hides_listing_and_photos_immediately(
    client: TestClient, network: dict[str, Any]
) -> None:
    listing, image_id = _join_and_share(client, network)
    partner = _auth(network["partner_token"])
    demand_id = _demand(client, network["partner_token"])
    client.put(
        f"/network/properties/{listing['id']}/share",
        headers=_auth(network["owner_token"]),
        json={"shared": False},
    )

    assert client.get(f"/network/search?demand_id={demand_id}", headers=partner).json() == []
    photo = client.get(
        f"/network/properties/{listing['id']}/images/{image_id}/content", headers=partner
    )
    assert photo.status_code == 404


def test_contacts_are_revealed_only_after_acceptance(
    client: TestClient, network: dict[str, Any]
) -> None:
    listing, _ = _join_and_share(client, network)
    partner = _auth(network["partner_token"])
    owner = _auth(network["owner_token"])

    created = client.post(
        "/network/partnerships",
        headers=partner,
        json={"property_id": listing["id"], "message": "Tenho um cliente pronto para visitar."},
    )
    assert created.status_code == 201, created.text
    request = created.json()
    assert request["status"] == "pending"
    assert request["counterpart_contact"] is None
    again = client.post(
        "/network/partnerships", headers=partner, json={"property_id": listing["id"]}
    )
    assert again.status_code == 409

    received = client.get("/network/partnerships", headers=owner).json()["received"]
    assert received[0]["counterpart_contact"] is None
    assert received[0]["message"] == "Tenho um cliente pronto para visitar."
    assert client.get("/network/settings", headers=owner).json()["pending_received"] == 1

    # Only the owner decides.
    assert (
        client.post(f"/network/partnerships/{request['id']}/accept", headers=partner).status_code
        == 403
    )
    accepted = client.post(f"/network/partnerships/{request['id']}/accept", headers=owner)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["counterpart_contact"]["phone"] == "51999990000"

    sent = client.get("/network/partnerships", headers=partner).json()["sent"][0]
    assert sent["status"] == "accepted"
    assert sent["partner_commission_percent"] == 50
    assert sent["counterpart_contact"]["agency_name"] == "Tenant dona-do-imovel"


def test_declined_request_can_be_made_again(client: TestClient, network: dict[str, Any]) -> None:
    listing, _ = _join_and_share(client, network)
    partner = _auth(network["partner_token"])
    request = client.post(
        "/network/partnerships", headers=partner, json={"property_id": listing["id"]}
    ).json()
    declined = client.post(
        f"/network/partnerships/{request['id']}/decline", headers=_auth(network["owner_token"])
    )
    assert declined.json()["status"] == "declined"
    assert declined.json()["counterpart_contact"] is None
    retry = client.post(
        "/network/partnerships", headers=partner, json={"property_id": listing["id"]}
    )
    assert retry.status_code == 201


def test_unsharing_cancels_pending_requests_and_blocks_acceptance(
    client: TestClient, network: dict[str, Any]
) -> None:
    listing, _ = _join_and_share(client, network)
    partner = _auth(network["partner_token"])
    owner = _auth(network["owner_token"])
    first = client.post(
        "/network/partnerships", headers=partner, json={"property_id": listing["id"]}
    ).json()

    client.put(f"/network/properties/{listing['id']}/share", headers=owner, json={"shared": False})
    received = client.get("/network/partnerships", headers=owner).json()["received"]
    assert received[0]["id"] == first["id"]
    assert received[0]["status"] == "cancelled"

    # Shared again, a new request is made; the listing is then deactivated before acceptance.
    client.put(f"/network/properties/{listing['id']}/share", headers=owner, json={"shared": True})
    second = client.post(
        "/network/partnerships", headers=partner, json={"property_id": listing["id"]}
    ).json()
    deactivated = client.patch(
        f"/properties/{listing['id']}/status", headers=owner, json={"status": "inactive"}
    )
    assert deactivated.status_code == 200, deactivated.text
    accepted = client.post(f"/network/partnerships/{second['id']}/accept", headers=owner)
    assert accepted.status_code == 409
    assert "não está mais" in accepted.json()["detail"]
