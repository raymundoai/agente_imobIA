import json
from datetime import UTC, datetime

import httpx

from app.modules.integrations.adapters.hubspot import HubSpotCrmAdapter
from app.modules.integrations.ports.crm import (
    CreateDealData,
    CreateNoteData,
    CreateOrUpdateContactData,
    CreateTaskData,
    CrmCredentials,
)


def test_hubspot_adapter_uses_bearer_auth_and_crm_object_paths() -> None:
    seen: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode() or "{}") if request.content else {}
        seen.append((request.method, request.url.path, body))
        assert request.headers["Authorization"] == "Bearer token"
        if request.url.path.endswith("/contacts/search"):
            return httpx.Response(200, json={"results": []})
        if request.url.path.endswith("/contacts"):
            return httpx.Response(201, json={"id": "contact-1", "properties": {}})
        if request.url.path.endswith("/deals"):
            return httpx.Response(201, json={"id": "deal-1", "properties": {}})
        if request.url.path.endswith("/notes"):
            return httpx.Response(201, json={"id": "note-1", "properties": {}})
        if request.url.path.endswith("/tasks"):
            return httpx.Response(201, json={"id": "task-1", "properties": {}})
        return httpx.Response(204)

    adapter = HubSpotCrmAdapter(httpx.Client(transport=httpx.MockTransport(handler)))
    credentials = CrmCredentials(
        base_url="https://api.hubapi.test",
        access_token="token",
        pipeline_id="pipeline",
        stage_ids={"qualified": "stage"},
    )

    assert adapter.search_contact_by_phone(credentials, "5511999999999") is None
    contact = adapter.create_contact(
        credentials, CreateOrUpdateContactData(name="Maria Silva", phone="5511999999999")
    )
    deal = adapter.create_deal(
        credentials, CreateDealData(name="Maria - Compra", pipeline="pipeline", stage="stage")
    )
    adapter.associate(credentials, "deal", deal.id, "contact", contact.id)
    adapter.add_note(
        credentials,
        CreateNoteData(body="Resumo", timestamp=datetime.now(UTC)),
        [("contact", contact.id)],
    )
    adapter.create_task(
        credentials,
        CreateTaskData(subject="Handoff", body="Ligar", timestamp=datetime.now(UTC)),
        [("deal", deal.id)],
    )

    paths = [path for _, path, _ in seen]
    assert "/crm/objects/2026-03/contacts/search" in paths
    assert "/crm/objects/2026-03/contacts" in paths
    assert "/crm/objects/2026-03/deals" in paths
    assert f"/crm/v4/objects/deals/{deal.id}/associations/default/contacts/{contact.id}" in paths
