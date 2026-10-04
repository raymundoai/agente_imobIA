import pytest
from fastapi.testclient import TestClient

from app.modules.ai.application.use_cases import DEFAULT_BASE_PROMPT
from tests.integration.test_asaas_billing import _platform_token
from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration


def test_prompt_versions_are_kept_and_default_text_is_not_stored(client: TestClient) -> None:
    platform = {"Authorization": f"Bearer {_platform_token(client)}"}
    initial = client.get("/platform/agent", headers=platform).json()
    assert initial["active"] is None
    assert initial["default_prompt"] == DEFAULT_BASE_PROMPT

    saved = client.post(
        "/platform/agent/versions",
        headers=platform,
        json={"base_prompt": "Seja breve.", "chat_model": "gpt-teste", "note": "teste A"},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["active"]["base_prompt"] == "Seja breve."

    restored = client.post(
        "/platform/agent/versions", headers=platform, json={"base_prompt": DEFAULT_BASE_PROMPT}
    ).json()
    assert restored["active"]["base_prompt"] is None
    assert [item["note"] for item in restored["versions"]] == [None, "teste A"]

    rejected = client.post(
        "/platform/agent/versions", headers=platform, json={"reasoning_effort": "turbo"}
    )
    assert rejected.status_code == 422


def test_client_instructions_enter_the_prompt_preview_and_need_platform_auth(
    client: TestClient,
) -> None:
    tenant, tenant_token = _provision(client, "agente-config")
    platform = {"Authorization": f"Bearer {_platform_token(client)}"}
    url = f"/platform/tenants/{tenant['id']}/agent"

    assert client.get(url, headers={"Authorization": f"Bearer {tenant_token}"}).status_code == 401
    updated = client.put(
        url, headers=platform, json={"extra_instructions": "Ofereça só imóveis acima de 1 milhão."}
    )
    assert updated.status_code == 200, updated.text
    preview = updated.json()["preview"]
    assert "Instruções específicas desta conta:\nOfereça só imóveis acima de 1 milhão." in preview
    assert DEFAULT_BASE_PROMPT in preview

    cleared = client.put(url, headers=platform, json={"extra_instructions": "  "}).json()
    assert cleared["extra_instructions"] == ""
    assert "Instruções específicas" not in cleared["preview"]
