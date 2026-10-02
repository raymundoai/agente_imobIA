from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.modules.contacts.models import ContactModel
from app.modules.conversations.adapters.models import ConversationModel
from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration


def _seed(client: TestClient, tenant_id: UUID) -> None:
    now = datetime.now(UTC)
    with client.app.state.container.database.session_factory() as session:
        for index, kind in enumerate(["lead", "lead", "owner"]):
            session.add(
                ContactModel(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    name=f"Contato {index}",
                    phone=f"55119999900{index}",
                    kind=kind,
                )
            )
        conversations = [
            (now, "ai", False),
            (now, "human", False),
            (now, "ai", True),  # WhatsApp group: not a started conversation
            (now - timedelta(days=3), "ai", False),
            (now - timedelta(days=40), "ai", False),
        ]
        for index, (started_at, mode, is_group) in enumerate(conversations):
            session.add(
                ConversationModel(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    channel="whatsapp",
                    phone=f"55118888800{index}",
                    mode=mode,
                    is_group=is_group,
                    started_at=started_at,
                    last_message_at=started_at,
                )
            )
        session.commit()


def test_dashboard_stats_and_conversation_timeline(client: TestClient) -> None:
    tenant, token = _provision(client, "tenant-a")
    auth = {"Authorization": f"Bearer {token}"}
    _seed(client, UUID(tenant["id"]))

    stats = client.get("/dashboard/stats", headers=auth)
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["contacts"] == 3
    assert body["contacts_by_kind"] == {"lead": 2, "owner": 1, "tenant": 0, "client": 0}
    assert body["conversations"] == 4

    week = client.get("/dashboard/conversations-timeline?days=7", headers=auth).json()
    assert len(week["points"]) == 7
    assert week["timezone"] == "America/Sao_Paulo"
    # AI and human conversations both count; groups and older ones do not.
    assert week["total"] == 3
    assert week["points"][-1]["conversations"] >= 1

    quarter = client.get("/dashboard/conversations-timeline?days=90", headers=auth).json()
    assert len(quarter["points"]) == 90
    assert quarter["total"] == 4

    invalid = client.get("/dashboard/conversations-timeline?days=15", headers=auth)
    assert invalid.status_code == 422


def test_dashboard_is_scoped_to_tenant(client: TestClient) -> None:
    tenant_a, _ = _provision(client, "tenant-a")
    _seed(client, UUID(tenant_a["id"]))
    _, token_b = _provision(client, "tenant-b")

    stats = client.get("/dashboard/stats", headers={"Authorization": f"Bearer {token_b}"})
    assert stats.json()["contacts"] == 0
    assert stats.json()["conversations"] == 0
