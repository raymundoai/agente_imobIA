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

    lead_contact = client.post(
        "/contacts",
        headers=auth_a,
        json={
            "name": "Carlos Comprador",
            "phone": "5511988887777",
            "kind": "lead",
            "tags": ["prioridade"],
        },
    ).json()
    demand = client.post(
        "/leads/demands",
        headers=auth_a,
        json={
            "lead_name": "Carlos Comprador",
            "phone": "5511988887777",
            "status": "qualified",
        },
    )
    assert demand.status_code == 201, demand.text
    filtered = client.get(f"/leads/demands?contact_id={lead_contact['id']}", headers=auth_a)
    assert filtered.status_code == 200, filtered.text
    assert [item["id"] for item in filtered.json()] == [demand.json()["id"]]
    assert (
        client.get(f"/leads/demands?contact_id={contact.json()['id']}", headers=auth_a).json() == []
    )
    assert (
        client.get(f"/leads/demands?contact_id={lead_contact['id']}", headers=auth_b).json() == []
    )


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


def test_lead_demand_can_only_be_deleted_by_its_own_tenant(client: TestClient) -> None:
    token_a = _provision(client, "demand-owner", "owner@example.com")
    token_b = _provision(client, "demand-other", "other@example.com")
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}
    created = client.post(
        "/leads/demands",
        headers=auth_a,
        json={
            "lead_name": "Cliente da demanda",
            "phone": "5511999887766",
            "purpose": "rent",
            "city": "São Paulo",
        },
    )
    assert created.status_code == 201, created.text
    demand_id = created.json()["id"]

    denied = client.delete(f"/leads/demands/{demand_id}", headers=auth_b)
    assert denied.status_code == 404
    assert len(client.get("/leads/demands", headers=auth_a).json()) == 1

    deleted = client.delete(f"/leads/demands/{demand_id}", headers=auth_a)
    assert deleted.status_code == 204, deleted.text
    assert client.get("/leads/demands", headers=auth_a).json() == []


def test_lead_demand_update_persists_state_and_validates_price_range(
    client: TestClient,
) -> None:
    token = _provision(client, "demand-state", "state@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/leads/demands",
        headers=auth,
        json={
            "lead_name": "Cliente estadual",
            "phone": "5551999001122",
            "purpose": "buy",
            "city": "Porto Alegre",
            "state": "rs",
            "price_min": 400000,
            "price_max": 800000,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["state"] == "RS"

    updated = client.patch(
        f"/leads/demands/{created.json()['id']}",
        headers=auth,
        json={"city": "São Paulo", "state": "sp"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["city"] == "São Paulo"
    assert updated.json()["state"] == "SP"

    invalid = client.patch(
        f"/leads/demands/{created.json()['id']}",
        headers=auth,
        json={"price_min": 900000},
    )
    assert invalid.status_code == 422


def test_federated_search_reuses_cache_and_releases_unstarted_reservation(
    client: TestClient,
) -> None:
    token = _provision(client, "search-cache-api", "search@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    demand = client.post(
        "/leads/demands",
        headers=auth,
        json={
            "lead_name": "Cliente da busca",
            "phone": "5551999770011",
            "purpose": "buy",
            "property_type": "apartamento",
            "city": "São Paulo",
            "state": "SP",
            "price_max": 900000,
        },
    )
    assert demand.status_code == 201, demand.text
    payload = {"demand_id": demand.json()["id"]}

    first = client.post("/capture/search-runs", headers=auth, json=payload)
    assert first.status_code == 202, first.text
    assert first.json()["cache_hit"] is False
    credits = client.get("/usage/credits", headers=auth)
    assert credits.status_code == 200, credits.text
    assert credits.json()["reserved_credits"] == 10
    commercial = client.get("/usage/commercial", headers=auth).json()
    standard = next(
        item for item in commercial["resources"] if item["resource"] == "property_search_standard"
    )
    assert standard["reserved"] == 1
    assert standard["measured"] == 0

    repeated = client.post("/capture/search-runs", headers=auth, json=payload)
    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["id"] == first.json()["id"]
    assert repeated.json()["cache_hit"] is True
    assert client.get("/usage/credits", headers=auth).json()["reserved_credits"] == 10
    commercial = client.get("/usage/commercial", headers=auth).json()
    standard = next(
        item for item in commercial["resources"] if item["resource"] == "property_search_standard"
    )
    assert standard["reserved"] == 1

    cancelled = client.post(
        f"/capture/search-runs/{first.json()['id']}/cancel",
        headers=auth,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert client.get("/usage/credits", headers=auth).json()["reserved_credits"] == 0
    commercial = client.get("/usage/commercial", headers=auth).json()
    standard = next(
        item for item in commercial["resources"] if item["resource"] == "property_search_standard"
    )
    assert standard["reserved"] == 0
    assert standard["measured"] == 0

    legacy = client.post(
        f"/capture/missions/{demand.json()['id']}/discover",
        headers=auth,
        json={"portal": "lello", "limit": 5},
    )
    assert legacy.status_code == 410


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


def test_property_video_upload_is_served_but_cannot_be_cover_or_optimized(
    client: TestClient,
) -> None:
    token = _provision(client, "tenant-video", "video@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/properties",
        headers=auth,
        json={
            "title": "Casa com vídeo",
            "purpose": "buy",
            "property_type": "casa",
            "category": "residential",
            "sale_price": 700000,
            "address": {
                "street": "Rua Vídeo",
                "neighborhood": "Centro",
                "city": "São Paulo",
                "state": "SP",
            },
        },
    )
    property_id = created.json()["id"]
    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isom"
    uploaded = client.post(
        f"/properties/{property_id}/images",
        headers=auth,
        files=[("files", ("tour.mp4", mp4, "video/mp4"))],
    )

    assert uploaded.status_code == 201, uploaded.text
    video = uploaded.json()[0]
    assert video["media_type"] == "video"
    assert video["original_content_type"] == "video/mp4"
    assert video["is_primary"] is False
    served = client.get(video["display_url"], headers=auth)
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("video/mp4")
    assert served.headers["content-length"] == str(len(mp4))
    assert served.content == mp4

    cover = client.patch(
        f"/properties/{property_id}/images/{video['id']}",
        headers=auth,
        json={"is_primary": True},
    )
    assert cover.status_code == 422
    optimized = client.post(
        f"/properties/{property_id}/images/{video['id']}/reprocess",
        headers=auth,
        json={"optimizations": []},
    )
    assert optimized.status_code == 422
    assert "somente para imagens" in optimized.json()["detail"]


def test_property_media_can_be_staged_committed_and_discarded(client: TestClient) -> None:
    token = _provision(client, "tenant-staging", "staging@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/properties",
        headers=auth,
        json={
            "title": "Casa com mídia preparada",
            "purpose": "buy",
            "property_type": "casa",
            "category": "residential",
            "sale_price": "750000.00",
            "address": {
                "street": "Rua Staging",
                "neighborhood": "Centro",
                "city": "São Paulo",
                "state": "SP",
            },
        },
    )
    property_id = created.json()["id"]
    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isom"

    staged = client.post(
        "/properties/media/staging",
        headers=auth,
        files={"file": ("tour.mp4", mp4, "video/mp4")},
    )
    assert staged.status_code == 201, staged.text
    committed = client.post(
        f"/properties/{property_id}/images/commit",
        headers=auth,
        json={"staging_ids": [staged.json()["id"]]},
    )
    assert committed.status_code == 201, committed.text
    media = committed.json()[0]
    assert client.get(media["display_url"], headers=auth).content == mp4
    assert (
        client.delete(f"/properties/media/staging/{staged.json()['id']}", headers=auth).status_code
        == 204
    )

    discardable = client.post(
        "/properties/media/staging",
        headers=auth,
        files={"file": ("descartar.mp4", mp4, "video/mp4")},
    )
    assert discardable.status_code == 201
    assert (
        client.delete(
            f"/properties/media/staging/{discardable.json()['id']}", headers=auth
        ).status_code
        == 204
    )


def test_property_image_order_and_primary_delete_are_atomic_and_isolated(
    client: TestClient,
) -> None:
    token = _provision(client, "tenant-a", "a@example.com")
    other_token = _provision(client, "tenant-b", "b@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/properties",
        headers=auth,
        json={
            "title": "Casa com galeria",
            "purpose": "buy",
            "property_type": "casa",
            "category": "residential",
            "sale_price": 750000,
            "address": {
                "street": "Rua Galeria",
                "neighborhood": "Centro",
                "city": "São Paulo",
                "state": "SP",
            },
        },
    )
    property_id = created.json()["id"]
    uploaded = client.post(
        f"/properties/{property_id}/images",
        headers=auth,
        files=[
            ("files", ("a.png", b"\x89PNG\r\n\x1a\na", "image/png")),
            ("files", ("b.png", b"\x89PNG\r\n\x1a\nb", "image/png")),
            ("files", ("c.png", b"\x89PNG\r\n\x1a\nc", "image/png")),
        ],
    ).json()
    original_order = {item["id"]: item["sort_order"] for item in uploaded}

    incomplete = client.put(
        f"/properties/{property_id}/images/order",
        headers=auth,
        json={"images": [{"id": uploaded[0]["id"], "sort_order": 9}]},
    )
    assert incomplete.status_code == 409
    unchanged = client.get(f"/properties/{property_id}/images", headers=auth).json()
    assert {item["id"]: item["sort_order"] for item in unchanged} == original_order

    isolated = client.put(
        f"/properties/{property_id}/images/order",
        headers={"Authorization": f"Bearer {other_token}"},
        json={
            "images": [
                {"id": item["id"], "sort_order": index}
                for index, item in enumerate(reversed(uploaded))
            ]
        },
    )
    assert isolated.status_code == 404

    reordered = client.put(
        f"/properties/{property_id}/images/order",
        headers=auth,
        json={
            "images": [
                {"id": item["id"], "sort_order": index}
                for index, item in enumerate(reversed(uploaded))
            ]
        },
    )
    assert reordered.status_code == 200, reordered.text
    assert {item["sort_order"] for item in reordered.json()} == {0, 1, 2}

    primary = next(item for item in reordered.json() if item["is_primary"])
    deleted = client.delete(f"/properties/{property_id}/images/{primary['id']}", headers=auth)
    assert deleted.status_code == 200, deleted.text
    remaining = deleted.json()
    assert len(remaining) == 2
    assert sum(item["is_primary"] for item in remaining) == 1
