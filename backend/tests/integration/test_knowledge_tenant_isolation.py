import base64

import pytest
from fastapi.testclient import TestClient

from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse

pytestmark = pytest.mark.integration


class FakeAiProvider(AiProviderPort):
    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        return AiProviderResponse(text="ok", model="fake", tokens_used=1)


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


def _encoded(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def test_knowledge_search_is_filtered_by_tenant(client: TestClient) -> None:
    client.app.state.container.ai_provider = FakeAiProvider()
    _, token_a = _provision(client, "tenant-a", "admin-a@example.com")
    _, token_b = _provision(client, "tenant-b", "admin-b@example.com")
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}

    uploaded_a = client.post(
        "/knowledge/documents",
        headers=auth_a,
        json={
            "filename": "faq-a.txt",
            "file_type": "text/plain",
            "content_base64": _encoded("Regra exclusiva do tenant A"),
        },
    )
    uploaded_b = client.post(
        "/knowledge/documents",
        headers=auth_b,
        json={
            "filename": "faq-b.txt",
            "file_type": "text/plain",
            "content_base64": _encoded("Regra exclusiva do tenant B"),
        },
    )
    assert uploaded_a.status_code == 201, uploaded_a.text
    assert uploaded_b.status_code == 201, uploaded_b.text
    assert uploaded_a.json()["status"] == "indexed"
    assert uploaded_b.json()["status"] == "indexed"

    search_a = client.post("/knowledge/search", headers=auth_a, json={"query": "regra"})
    search_b = client.post("/knowledge/search", headers=auth_b, json={"query": "regra"})
    assert search_a.status_code == 200, search_a.text
    assert search_b.status_code == 200, search_b.text

    contents_a = [item["content"] for item in search_a.json()["results"]]
    contents_b = [item["content"] for item in search_b.json()["results"]]
    assert contents_a == ["Regra exclusiva do tenant A"]
    assert contents_b == ["Regra exclusiva do tenant B"]


def test_only_admin_can_manage_knowledge_documents(client: TestClient) -> None:
    _, admin_token = _provision(client, "knowledge-roles", "admin@knowledge.example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/users",
        headers=admin_headers,
        json={
            "name": "Corretora",
            "email": "corretora@knowledge.example.com",
            "password": "valid-test-password-123",
            "role": "corretor",
        },
    )
    assert created.status_code == 201, created.text
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "knowledge-roles",
            "email": "corretora@knowledge.example.com",
            "password": "valid-test-password-123",
        },
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/knowledge/documents",
        headers=headers,
        json={
            "filename": "faq.txt",
            "file_type": "txt",
            "content_base64": _encoded("conteúdo"),
        },
    )

    assert response.status_code == 403, response.text
