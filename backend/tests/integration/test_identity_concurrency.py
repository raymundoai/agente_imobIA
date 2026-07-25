from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.modules.contacts.service import ContactUpsertService
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.application.use_cases import LeadQualificationService
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository

pytestmark = pytest.mark.integration


def _provision(client: TestClient) -> tuple[str, str]:
    password = "valid-test-password-123"
    created = client.post(
        "/tenants",
        json={
            "name": "Concorrência",
            "slug": "concorrencia",
            "admin_name": "Admin",
            "admin_email": "admin@concorrencia.example.com",
            "admin_password": password,
        },
    )
    assert created.status_code == 201
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "concorrencia",
            "email": "admin@concorrencia.example.com",
            "password": password,
        },
    )
    return created.json()["id"], login.json()["access_token"]


def test_concurrent_manual_demands_keep_single_open_identity(client: TestClient) -> None:
    _, token = _provision(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "lead_name": "Lead simultâneo",
        "phone": "+55 (11) 98888-7777",
        "purpose": "buy",
        "property_type": "apartamento",
        "city": "São Paulo",
        "neighborhoods": ["Centro"],
        "price_max": 900000,
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: client.post("/leads/demands", headers=headers, json=payload),
                range(2),
            )
        )

    assert sorted(response.status_code for response in responses) == [201, 409]
    demands = client.get("/leads/demands", headers=headers).json()
    assert len(demands) == 1
    assert demands[0]["phone"] == "5511988887777"


def test_concurrent_contact_creation_returns_conflict_instead_of_integrity_error(
    client: TestClient,
) -> None:
    _, token = _provision(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": "Contato simultâneo",
        "phone": "5511977776666",
        "kind": "lead",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: client.post("/contacts", headers=headers, json=payload),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [201, 409]


def test_manual_creation_and_ai_qualification_share_global_lock_order(
    client: TestClient,
) -> None:
    tenant_id, token = _provision(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "lead_name": "Lead cruzado",
        "phone": "+55 (11) 96666-5555",
        "purpose": "buy",
        "property_type": "casa",
        "city": "São Paulo",
        "neighborhoods": ["Centro"],
        "price_max": 700000,
    }

    def qualify_with_ai() -> str:
        session = client.app.state.container.database.session_factory()
        try:
            service = LeadQualificationService(
                SqlAlchemyTenantRepository(session),
                SqlAlchemyLeadDemandRepository(session),
                client.app.state.container.crm_credentials,
                client.app.state.container.crm,
                client.app.state.container.event_bus,
                ContactUpsertService(session),
            )
            return str(
                service.create_or_update_lead(
                    tenant_id,
                    {**payload, "phone": "5511966665555"},
                ).id
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        manual = executor.submit(client.post, "/leads/demands", headers=headers, json=payload)
        qualification = executor.submit(qualify_with_ai)
        manual_response = manual.result(timeout=10)
        qualification.result(timeout=10)

    assert manual_response.status_code in {201, 409}
    demands = client.get("/leads/demands", headers=headers).json()
    assert len(demands) == 1
    assert demands[0]["phone"] == "5511966665555"
    assert demands[0]["status"] == "qualified"
