import pytest

from app.modules.ai.application.use_cases import ProcessKnowledgeDocumentUseCase
from app.modules.conversations.application.use_cases import lead_agent_is_active
from app.modules.tenants.api.schemas import TenantResponse
from app.modules.tenants.domain.entities import Tenant


def test_tenant_response_redacts_nested_credentials() -> None:
    tenant = Tenant(
        name="Teste",
        slug="teste",
        settings={
            "integrations": {
                "evolution": {
                    "status": "connected",
                    "webhook_secret_encrypted": "ciphertext",
                    "api_key": "private",
                }
            }
        },
    )

    settings = TenantResponse.from_domain(tenant).settings

    assert settings["integrations"]["evolution"] == {"status": "connected"}


def test_agent_must_be_globally_active_and_bound_to_the_incoming_channel() -> None:
    settings = {
        "agents": {"leads": {"status": "active"}},
        "channels": {
            "whatsapp": {"agents": []},
            "telegram": {"agents": ["leads"]},
        },
    }

    assert lead_agent_is_active(settings, "whatsapp") is False
    assert lead_agent_is_active(settings, "telegram") is True
    settings["agents"]["leads"]["status"] = "inactive"
    assert lead_agent_is_active(settings, "telegram") is False


def test_knowledge_processing_rejects_excessive_extracted_text_before_embeddings() -> None:
    use_case = ProcessKnowledgeDocumentUseCase(None, None, None, None, max_words=2)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="50 mil palavras"):
        use_case._chunk_text("uma duas três")
