from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from app.modules.ai.adapters.repositories import SqlAlchemyAiAuditLogRepository
from app.modules.integrations.adapters.persistent_credentials import (
    PersistentEvolutionCredentialsProvider,
)
from app.modules.integrations.ports.message_channel import (
    MessageChannelPort,
    SentChannelMessage,
)
from app.modules.messaging.processor import MessageJobProcessor
from app.modules.messaging.service import MessageJobRepository
from app.shared.security.secrets import SecretCipher
from tests.conftest import TEST_WEBHOOK_SECRET
from tests.integration.test_whatsapp_webhook_idempotency import (
    FakeAutoReplyAi,
    _payload,
    _provision,
)

pytestmark = pytest.mark.integration


class CountingChannel(MessageChannelPort):
    def __init__(self) -> None:
        self.sent = 0
        self.keys: list[str | None] = []

    def receive_message(self, payload):
        raise NotImplementedError

    def send_message(
        self, credentials, phone, text, *, idempotency_key=None
    ) -> SentChannelMessage:
        self.sent += 1
        self.keys.append(idempotency_key)
        return SentChannelMessage(external_message_id=f"remote-{self.sent}")


def _enqueue(client: TestClient, external_id: str) -> str:
    response = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=_payload(external_id),
    )
    assert response.status_code == 200
    return response.json()["job_id"]


def test_two_workers_cannot_claim_the_same_job(client: TestClient) -> None:
    _provision(client, "tenant-a")
    client.app.state.container.settings.ai_auto_reply_enabled = True
    _enqueue(client, "multiworker-1")
    database = client.app.state.container.database

    with database.session_factory() as first:
        claimed = MessageJobRepository(first).claim_next(300, "worker-a")
    with database.session_factory() as second:
        other = MessageJobRepository(second).claim_next(300, "worker-b")

    assert claimed is not None
    assert other is None
    assert claimed.lease_owner == "worker-a"
    assert claimed.lease_token is not None


def test_generation_crash_reuses_persisted_outbound_and_charge(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    client.app.state.container.ai_provider = FakeAutoReplyAi()
    client.app.state.container.settings.ai_auto_reply_enabled = True
    client.app.state.container.settings.ai_auto_send_to_channel = False
    job_id = _enqueue(client, "generation-recovery-1")
    processor = MessageJobProcessor(client.app.state.container, "worker-a")
    assert processor.process_next()["status"] == "sent"

    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE message_jobs SET status='retrying', stage='generation', "
                "available_at=now(), lease_token=NULL, lease_owner=NULL, "
                "lease_expires_at=NULL WHERE id=:id"
            ),
            {"id": job_id},
        )
    client.app.state.container.ai_provider = None
    recovered = MessageJobProcessor(
        client.app.state.container, "worker-b"
    ).process_next()
    assert recovered["status"] == "sent"
    assert recovered["recovered"] is True
    with engine.connect() as connection:
        counts = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM messages WHERE id=:id), "
                "(SELECT count(*) FROM credit_ledger "
                "WHERE tenant_id=:tenant_id AND kind='usage')"
            ),
            {"id": job_id, "tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert counts[0] == 1
    assert counts[1] == 1


def test_expired_delivery_lease_becomes_unknown_without_resend(
    client: TestClient,
) -> None:
    _provision(client, "tenant-a")
    client.app.state.container.ai_provider = FakeAutoReplyAi()
    client.app.state.container.settings.ai_auto_reply_enabled = True
    client.app.state.container.settings.ai_auto_send_to_channel = True
    _enqueue(client, "delivery-crash-1")
    processor = MessageJobProcessor(client.app.state.container, "generator")
    assert processor.process_next()["status"] == "delivery_pending"
    database = client.app.state.container.database

    with database.session_factory() as session:
        claimed = MessageJobRepository(session).claim_next(300, "dead-worker")
        assert claimed is not None
        claimed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    with database.session_factory() as session:
        next_job = MessageJobRepository(session).claim_next(300, "new-worker")
        assert next_job is None
        status = session.scalar(
            text("SELECT status FROM message_jobs WHERE id=:id"),
            {"id": claimed.id},
        )
    assert status == "delivery_unknown"


def test_message_job_operations_require_admin_or_manager(client: TestClient) -> None:
    _, admin_token = _provision(client, "tenant-a")
    created = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Corretor",
            "email": "corretor@example.com",
            "password": "valid-test-password-456",
            "role": "corretor",
        },
    )
    assert created.status_code == 201
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "tenant-a",
            "email": "corretor@example.com",
            "password": "valid-test-password-456",
        },
    )
    token = login.json()["access_token"]
    denied = client.get(
        "/message-jobs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 403
    evolution_denied = client.post(
        "/integrations/evolution/whatsapp/connect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert evolution_denied.status_code == 403
    assert (
        client.post(
            "/message-jobs/process-next",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).status_code
        == 404
    )


def test_crash_after_remote_send_is_not_automatically_resent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _provision(client, "tenant-a")
    client.app.state.container.ai_provider = FakeAutoReplyAi()
    client.app.state.container.settings.ai_auto_reply_enabled = True
    client.app.state.container.settings.ai_auto_send_to_channel = True
    fake_channel = CountingChannel()
    job_id = _enqueue(client, "send-complete-crash-1")
    client.app.state.container.message_channel = fake_channel
    processor = MessageJobProcessor(client.app.state.container, "worker-a")
    assert processor.process_next()["status"] == "delivery_pending"

    def crash_before_complete(*args, **kwargs):
        raise RuntimeError("simulated crash before local complete")

    monkeypatch.setattr(MessageJobRepository, "mark_delivery_part", crash_before_complete)
    result = processor.process_next()
    assert result["status"] == "delivery_unknown"
    assert fake_channel.sent == 1
    assert fake_channel.keys == [f"{job_id}:0"]
    assert processor.process_next() is None


def test_handoff_outbound_and_billing_roll_back_together_on_audit_failure(
    client: TestClient,
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    client.app.state.container.ai_provider = FakeAutoReplyAi()
    client.app.state.container.settings.ai_auto_reply_enabled = True
    payload = _payload("handoff-rollback-1")
    payload["data"]["message"]["conversation"] = "Quero cancelar contrato"
    response = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=payload,
    )
    conversation_id = response.json()["conversation_id"]

    def fail_audit(*args, **kwargs):
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(SqlAlchemyAiAuditLogRepository, "create", fail_audit)
    processed = MessageJobProcessor(
        client.app.state.container, "rollback-worker"
    ).process_next()
    assert processed["status"] == "retrying"

    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT "
                "(SELECT mode FROM conversations WHERE id=:conversation_id), "
                "(SELECT count(*) FROM messages WHERE conversation_id=:conversation_id "
                "AND direction='outbound'), "
                "(SELECT count(*) FROM credit_ledger WHERE tenant_id=:tenant_id)"
            ),
            {"conversation_id": conversation_id, "tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert state == ("ai", 0, 0)


def test_persistent_provider_survives_restart_and_previous_key_rotation(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    encrypted = SecretCipher("previous-integration-key").encrypt("stored-webhook-secret")
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE tenants SET settings=jsonb_build_object("
                "'integrations', jsonb_build_object('evolution', jsonb_build_object("
                "'instance', 'persisted-instance', "
                "'webhook_secret_encrypted', CAST(:encrypted AS text)))) "
                "WHERE id=:tenant_id"
            ),
            {"encrypted": encrypted, "tenant_id": tenant["id"]},
        )
    engine.dispose()
    settings = client.app.state.container.settings.model_copy(
        update={
            "evolution_base_url": "https://evolution.example.com",
            "evolution_api_key": SecretStr("global-api-key"),
            "integration_secret_key": SecretStr("current-integration-key"),
            "integration_secret_previous_keys": [
                SecretStr("previous-integration-key")
            ],
        }
    )

    first_process = PersistentEvolutionCredentialsProvider(
        client.app.state.container.database, settings
    ).get("tenant-a")
    restarted_process = PersistentEvolutionCredentialsProvider(
        client.app.state.container.database, settings
    ).get("tenant-a")

    assert first_process is not None
    assert restarted_process is not None
    assert restarted_process.instance == "persisted-instance"
    assert restarted_process.webhook_secret == "stored-webhook-secret"
