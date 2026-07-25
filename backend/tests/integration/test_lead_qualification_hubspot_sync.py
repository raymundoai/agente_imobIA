from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse, AiToolCall
from app.modules.integrations.ports.crm import (
    CreateDealData,
    CreateNoteData,
    CreateOrUpdateContactData,
    CreateTaskData,
    CrmContact,
    CrmCredentials,
    CrmDeal,
    CrmPort,
)
from tests.conftest import TEST_WEBHOOK_SECRET

pytestmark = pytest.mark.integration


class FakeAiProvider(AiProviderPort):
    def __init__(self) -> None:
        self.calls = 0

    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return AiProviderResponse(
                text="",
                model="fake-model",
                tokens_used=10,
                tool_calls=[
                    AiToolCall(
                        name="create_or_update_lead",
                        arguments={
                            "lead_name": "Maria Silva",
                            "phone": "5511888888888",
                            "email": None,
                            "purpose": "buy",
                            "property_type": "apartamento",
                            "city": "São Paulo",
                            "neighborhoods": ["Pinheiros"],
                            "price_min": 500000,
                            "price_max": 800000,
                            "bedrooms": 2,
                            "parking_spaces": 1,
                            "min_area": None,
                            "notes": "Lead pronto",
                            "handoff_reason": "lead pronto para corretor",
                        },
                    )
                ],
            )
        return AiProviderResponse(
            text="Vou encaminhar para um corretor.", model="fake-model", tokens_used=12
        )


class FakeCrm(CrmPort):
    def __init__(self) -> None:
        self.created_contacts: list[CreateOrUpdateContactData] = []
        self.created_deals: list[CreateDealData] = []
        self.notes: list[CreateNoteData] = []
        self.tasks: list[CreateTaskData] = []
        self.associations: list[tuple[str, str, str, str]] = []

    def search_contact_by_phone(self, credentials: CrmCredentials, phone: str):
        return None

    def create_contact(self, credentials: CrmCredentials, data: CreateOrUpdateContactData):
        self.created_contacts.append(data)
        return CrmContact(id="contact-1", properties={})

    def update_contact(self, credentials: CrmCredentials, contact_id: str, data):
        raise AssertionError("unexpected update")

    def create_deal(self, credentials: CrmCredentials, data: CreateDealData):
        self.created_deals.append(data)
        return CrmDeal(id="deal-1", properties={})

    def associate(
        self, credentials, from_object_type, from_object_id, to_object_type, to_object_id
    ):
        self.associations.append((from_object_type, from_object_id, to_object_type, to_object_id))

    def add_note(self, credentials, data: CreateNoteData, associations):
        self.notes.append(data)
        return "note-1"

    def create_task(self, credentials, data: CreateTaskData, associations):
        self.tasks.append(data)
        return "task-1"


def _provision(client: TestClient, slug: str) -> tuple[str, str]:
    password = "valid-test-password-123"
    created = client.post(
        "/tenants",
        json={
            "name": slug,
            "slug": slug,
            "admin_name": "Admin",
            "admin_email": "admin@example.com",
            "admin_password": password,
        },
    )
    assert created.status_code == 201, created.text
    login = client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": "admin@example.com", "password": password},
    )
    assert login.status_code == 200
    return created.json()["id"], login.json()["access_token"]


def _receive(client: TestClient, slug: str) -> dict[str, Any]:
    response = client.post(
        f"/webhooks/whatsapp/{slug}",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json={
            "event": "MESSAGES_UPSERT",
            "data": {
                "key": {
                    "id": "lead-msg-1",
                    "remoteJid": "5511888888888@s.whatsapp.net",
                    "fromMe": False,
                },
                "message": {"conversation": "Quero comprar apartamento em Pinheiros"},
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_ai_lead_qualification_syncs_hubspot_and_persists_lead(
    client: TestClient, migrated_database: str
) -> None:
    fake_crm = FakeCrm()
    client.app.state.container.ai_provider = FakeAiProvider()
    client.app.state.container.crm = fake_crm
    tenant_id, token = _provision(client, "tenant-a")
    conversation_id = _receive(client, "tenant-a")["conversation_id"]

    response = client.post(
        f"/ai/conversations/{conversation_id}/respond",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_to_channel": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["tools_called"][0]["name"] == "create_or_update_lead"
    assert fake_crm.created_contacts[0].phone == "5511888888888"
    assert fake_crm.created_deals[0].pipeline == "pipeline-a"
    assert fake_crm.notes
    assert fake_crm.tasks
    assert ("deal", "deal-1", "contact", "contact-1") in fake_crm.associations

    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT lead_name, crm_contact_id, crm_deal_id, contact_id, conversation_id "
                "FROM lead_demands "
                "WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        ).one()
        contact = connection.execute(
            text(
                "SELECT name, phone, interest, notes FROM contacts "
                "WHERE tenant_id = :tenant_id AND id = :contact_id"
            ),
            {"tenant_id": tenant_id, "contact_id": row.contact_id},
        ).one()
    engine.dispose()
    assert row.crm_contact_id == "contact-1"
    assert row.crm_deal_id == "deal-1"
    assert row.lead_name == "Maria Silva"
    assert str(row.conversation_id) == conversation_id
    assert contact.name == "Maria Silva"
    assert contact.phone == "5511888888888"
    assert "apartamento" in contact.interest
    assert contact.notes == "Lead pronto"
