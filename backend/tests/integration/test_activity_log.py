import pytest
from fastapi.testclient import TestClient

from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_deleted_demand_stays_in_the_history_with_who_and_what(client: TestClient) -> None:
    _, token = _provision(client, "historico")
    created = client.post(
        "/leads/demands",
        headers=_auth(token),
        json={
            "lead_name": "Cliente Apagado",
            "phone": "51991112222",
            "purpose": "rent",
            "property_type": "apartamento",
            "city": "Porto Alegre",
        },
    )
    assert created.status_code == 201, created.text
    # Typed without the country code, the number is stored the way WhatsApp reports it.
    assert created.json()["phone"] == "5551991112222"

    assert (
        client.delete(f"/leads/demands/{created.json()['id']}", headers=_auth(token)).status_code
        == 204
    )

    history = client.get("/activity", headers=_auth(token)).json()
    assert len(history) == 1
    entry = history[0]
    assert entry["entity"] == "lead_demand"
    assert entry["action"] == "deleted"
    assert entry["actor_type"] == "user"
    assert entry["actor_name"]
    assert (
        entry["summary"]
        == "Demanda de Cliente Apagado excluída: Aluguel de apartamento em Porto Alegre"
    )
    assert entry["snapshot"]["phone"] == "5551991112222"


def test_history_is_for_managers_only(client: TestClient) -> None:
    tenant, token = _provision(client, "historico-acesso")
    password = "valid-broker-password-123"
    invited = client.post(
        "/users",
        headers=_auth(token),
        json={
            "name": "Corretora",
            "email": "corretora@historico.example.com",
            "role": "corretor",
            "password": password,
        },
    )
    assert invited.status_code in (200, 201), invited.text
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": tenant["slug"],
            "email": "corretora@historico.example.com",
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    broker = _auth(login.json()["access_token"])
    assert client.get("/activity", headers=broker).status_code == 403
    assert client.get("/activity", headers=_auth(token)).status_code == 200


def test_whatsapp_number_without_ninth_digit_finds_the_typed_contact(client: TestClient) -> None:
    _, token = _provision(client, "nono-digito")
    created = client.post(
        "/contacts",
        headers=_auth(token),
        json={"name": "Felipe", "phone": "51991129452", "kind": "lead"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["phone"] == "5551991129452"

    duplicate = client.post(
        "/contacts",
        headers=_auth(token),
        json={"name": "Felipe de novo", "phone": "555191129452", "kind": "lead"},
    )
    assert duplicate.status_code == 409

    demand = client.post(
        "/leads/demands",
        headers=_auth(token),
        json={"lead_name": "Felipe", "phone": "555191129452", "purpose": "buy"},
    )
    assert demand.status_code == 201, demand.text
    assert demand.json()["contact_id"] == created.json()["id"]


def test_deleting_a_contact_keeps_its_conversation_history_and_logs_it(
    client: TestClient,
) -> None:
    _, token = _provision(client, "excluir-contato")
    demand = client.post(
        "/leads/demands",
        headers=_auth(token),
        json={"lead_name": "Contato Teste", "phone": "51988887777", "purpose": "buy"},
    ).json()
    contact_id = demand["contact_id"]

    deleted = client.delete(f"/contacts/{contact_id}", headers=_auth(token))
    assert deleted.status_code == 204, deleted.text
    assert client.delete(f"/contacts/{contact_id}", headers=_auth(token)).status_code == 404

    kept = client.get(f"/leads/demands/{demand['id']}", headers=_auth(token))
    assert kept.status_code == 200
    assert kept.json()["contact_id"] is None

    entry = client.get("/activity?entity=contact", headers=_auth(token)).json()[0]
    assert entry["summary"] == "Contato excluído: Contato Teste (1 demanda continua no sistema)"
    assert entry["snapshot"]["phone"] == "5551988887777"
