from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.modules.ai.domain.ports import (
    AiProviderDispatchUncertainError,
    AiProviderPort,
    AiProviderRejectedError,
    AiProviderResponse,
    AiToolCall,
)
from app.modules.billing_usage.service import (
    CreditCharge,
    CreditLedgerService,
    CreditReservationClosed,
    chat_charge,
    estimated_chat_charge,
)
from app.modules.messaging.processor import MessageJobProcessor
from app.modules.properties.media import ImageEditResult
from app.shared.errors.exceptions import PaymentRequiredError
from tests.conftest import TEST_WEBHOOK_SECRET
from tests.integration.test_whatsapp_webhook_idempotency import (
    FakeAutoReplyAi,
    _payload,
    _provision,
)

pytestmark = pytest.mark.integration


class CountingFailAi(AiProviderPort):
    def __init__(self) -> None:
        self.calls = 0

    def get_embedding(self, text: str) -> list[float]:
        self.calls += 1
        raise RuntimeError("provider failed")

    def chat_completion(self, *, system_prompt, messages, tools):
        raise AssertionError


class CountingImageAi(FakeAutoReplyAi):
    def __init__(self) -> None:
        self.image_calls = 0

    def edit_image(self, content: bytes, *, filename: str, prompt: str) -> ImageEditResult:
        self.image_calls += 1
        return ImageEditResult(
            content=b"\x89PNG\r\n\x1a\nresult",
            input_image_tokens=100,
            input_text_tokens=10,
            output_image_tokens=100,
        )


class DispatchFailureAi(FakeAutoReplyAi):
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.chat_calls = 0

    def chat_completion(self, *, system_prompt, messages, tools):
        self.chat_calls += 1
        raise self.error


class ToolThenRejectedAi(FakeAutoReplyAi):
    def __init__(self) -> None:
        self.chat_calls = 0

    def chat_completion(self, *, system_prompt, messages, tools):
        self.chat_calls += 1
        if self.chat_calls == 1:
            return AiProviderResponse(
                text="",
                model="gpt-5.4-mini",
                tokens_used=30,
                input_tokens=20,
                output_tokens=10,
                tool_calls=[
                    AiToolCall(
                        name="request_human_handoff",
                        arguments={"reason": "requested"},
                    )
                ],
            )
        raise AiProviderRejectedError("rate limited")


def _enqueue(client: TestClient, external_id: str) -> None:
    response = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=_payload(external_id),
    )
    assert response.status_code == 200


def _account(database_url: str, tenant_id: str, **values: object) -> None:
    assignments = ", ".join(f"{key}=:{key}" for key in values)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO credit_accounts (tenant_id) VALUES (:tenant_id) "
                "ON CONFLICT (tenant_id) DO NOTHING"
            ),
            {"tenant_id": tenant_id},
        )
        connection.execute(
            text(f"UPDATE credit_accounts SET {assignments} WHERE tenant_id=:tenant_id"),
            {"tenant_id": tenant_id, **values},
        )
    engine.dispose()


def test_insufficient_balance_prevents_openai_call(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    _account(
        migrated_database,
        tenant["id"],
        enforcement_mode="enforce",
        balance_credits=0,
    )
    ai = CountingFailAi()
    client.app.state.container.ai_provider = ai
    client.app.state.container.settings.ai_auto_reply_enabled = True
    _enqueue(client, "no-credit-1")

    result = MessageJobProcessor(client.app.state.container, "credit-worker").process_next()

    assert result["status"] == "retrying"
    assert "insuficientes" in result["error"]
    assert ai.calls == 0


def test_unknown_model_is_rejected_before_openai_call(client: TestClient) -> None:
    _provision(client, "tenant-a")
    ai = CountingFailAi()
    client.app.state.container.ai_provider = ai
    client.app.state.container.settings.ai_auto_reply_enabled = True
    client.app.state.container.settings.openai_chat_model = "unknown-unpriced-model"
    _enqueue(client, "unknown-model-1")

    result = MessageJobProcessor(client.app.state.container, "catalog-worker").process_next()

    assert result["status"] == "retrying"
    assert "tarifa" in result["error"]
    assert ai.calls == 0


def test_concurrent_reservations_cannot_oversubscribe_balance(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    estimate = estimated_chat_charge("gpt-5.4-mini")
    _account(
        migrated_database,
        tenant["id"],
        enforcement_mode="enforce",
        balance_credits=estimate.credits,
    )
    database = client.app.state.container.database

    def reserve(key: str) -> str:
        try:
            with database.session_factory() as session:
                CreditLedgerService(session).reserve(
                    UUID(tenant["id"]),
                    resource="ai_message",
                    model="gpt-5.4-mini",
                    estimate=estimate,
                    idempotency_key=key,
                    reference_id=None,
                )
            return "reserved"
        except PaymentRequiredError:
            return "denied"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, ("concurrent-a", "concurrent-b")))
    assert sorted(outcomes) == ["denied", "reserved"]


def test_embedding_failure_before_chat_dispatch_releases_for_safe_retry(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    ai = CountingFailAi()
    client.app.state.container.ai_provider = ai
    client.app.state.container.settings.ai_auto_reply_enabled = True
    _enqueue(client, "provider-failure-1")
    result = MessageJobProcessor(client.app.state.container, "failure-worker").process_next()
    assert result["status"] == "retrying"
    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT ca.reserved_credits, cr.status "
                "FROM credit_accounts ca JOIN credit_reservations cr "
                "ON cr.tenant_id=ca.tenant_id WHERE ca.tenant_id=:tenant_id"
            ),
            {"tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert state == (0, "released")


@pytest.mark.parametrize(
    ("error", "expected_job", "expected_reservation"),
    [
        (AiProviderRejectedError("bad request"), "retrying", "released"),
        (
            AiProviderDispatchUncertainError("timeout"),
            "failed",
            "started",
        ),
    ],
)
def test_chat_dispatch_classification_controls_billing_and_retry(
    client: TestClient,
    migrated_database: str,
    error: Exception,
    expected_job: str,
    expected_reservation: str,
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    ai = DispatchFailureAi(error)
    client.app.state.container.ai_provider = ai
    client.app.state.container.settings.ai_auto_reply_enabled = True
    _enqueue(client, f"dispatch-{expected_job}")
    result = MessageJobProcessor(client.app.state.container, "dispatch-worker").process_next()
    assert result["status"] == expected_job
    assert ai.chat_calls == 1
    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT ca.reserved_credits, cr.status FROM credit_accounts ca "
                "JOIN credit_reservations cr ON ca.tenant_id=cr.tenant_id "
                "WHERE ca.tenant_id=:tenant_id"
            ),
            {"tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert state[1] == expected_reservation
    assert (state[0] == 0) is (expected_reservation == "released")


def test_second_call_rejection_settles_first_call_without_retrying_it(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    ai = ToolThenRejectedAi()
    client.app.state.container.ai_provider = ai
    client.app.state.container.settings.ai_auto_reply_enabled = True
    _enqueue(client, "tool-then-429")
    result = MessageJobProcessor(client.app.state.container, "multi-call-worker").process_next()
    assert result["status"] == "failed"
    assert ai.chat_calls == 2
    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT cr.status, cr.extra->>'accepted_call_count', "
                "cl.extra->>'partial_usage', count(cl.id) OVER () "
                "FROM credit_reservations cr JOIN credit_ledger cl "
                "ON cr.tenant_id=cl.tenant_id WHERE cr.tenant_id=:tenant_id"
            ),
            {"tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert state == ("settled", "1", "true", 1)
    assert MessageJobProcessor(client.app.state.container, "second-worker").process_next() is None
    assert ai.chat_calls == 2


@pytest.mark.parametrize(
    ("mode", "unlimited", "expected_delta"),
    [("meter_only", False, -1), ("enforce", True, 0)],
)
def test_meter_only_and_unlimited_keep_usage_telemetry(
    client: TestClient,
    migrated_database: str,
    mode: str,
    unlimited: bool,
    expected_delta: int,
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    _account(
        migrated_database,
        tenant["id"],
        enforcement_mode=mode,
        balance_credits=0,
        unlimited_messages=unlimited,
    )
    client.app.state.container.ai_provider = FakeAutoReplyAi()
    client.app.state.container.settings.ai_auto_reply_enabled = True
    _enqueue(client, f"telemetry-{mode}-{unlimited}")
    result = MessageJobProcessor(client.app.state.container, "telemetry-worker").process_next()
    assert result["status"] == "sent"
    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT "
                "(SELECT delta_credits FROM credit_ledger WHERE tenant_id=:tenant_id), "
                "(SELECT count(*) FROM usage_records WHERE tenant_id=:tenant_id "
                "AND type='ai_call'), "
                "(SELECT status FROM credit_reservations WHERE tenant_id=:tenant_id)"
            ),
            {"tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert state == (expected_delta, 1, "settled")


def test_image_insufficient_balance_returns_402_before_openai(
    client: TestClient, migrated_database: str
) -> None:
    tenant, token = _provision(client, "tenant-a")
    _account(
        migrated_database,
        tenant["id"],
        enforcement_mode="enforce",
        balance_credits=0,
    )
    ai = CountingImageAi()
    client.app.state.container.ai_provider = ai
    auth = {"Authorization": f"Bearer {token}"}
    property_id = _create_property_for_image(client, auth)
    upload = client.post(
        f"/properties/{property_id}/images",
        headers=auth,
        files={"files": ("foto.png", b"\x89PNG\r\n\x1a\nsource", "image/png")},
    )
    image_id = upload.json()[0]["id"]
    response = client.post(
        f"/properties/{property_id}/images/{image_id}/reprocess",
        headers=auth,
        json={"optimizations": ["iluminação"]},
    )
    assert response.status_code == 402
    assert ai.image_calls == 0


def test_image_billing_idempotency_prevents_duplicate_openai_cost(
    client: TestClient,
) -> None:
    _, token = _provision(client, "tenant-a")
    ai = CountingImageAi()
    client.app.state.container.ai_provider = ai
    auth = {"Authorization": f"Bearer {token}"}
    property_id = _create_property_for_image(client, auth)
    upload = client.post(
        f"/properties/{property_id}/images",
        headers=auth,
        files={"files": ("foto.png", b"\x89PNG\r\n\x1a\nsource", "image/png")},
    )
    image_id = upload.json()[0]["id"]
    url = f"/properties/{property_id}/images/{image_id}/reprocess"
    operation_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    payload = {"operation_id": operation_id, "optimizations": ["iluminação"]}
    first = client.post(url, headers=auth, json=payload)
    second = client.post(url, headers=auth, json=payload)
    retry = client.post(
        url,
        headers=auth,
        json={
            "operation_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "optimizations": ["iluminação"],
        },
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert retry.status_code == 200, retry.text
    assert ai.image_calls == 2
    commercial = client.get("/usage/commercial", headers=auth).json()
    image_usage = next(
        item for item in commercial["resources"] if item["resource"] == "image_optimization"
    )
    assert image_usage["measured"] == 2
    assert image_usage["consumed"] == 2
    assert image_usage["available"] == 28


def _create_property_for_image(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/properties",
        headers=headers,
        json={
            "title": "Imóvel para imagem",
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
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_expired_crash_reservation_is_reconciled(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    estimate = estimated_chat_charge("gpt-5.4-mini")
    with client.app.state.container.database.session_factory() as session:
        CreditLedgerService(session).reserve(
            UUID(tenant["id"]),
            resource="ai_message",
            model="gpt-5.4-mini",
            estimate=estimate,
            idempotency_key="crashed-operation",
            reference_id=None,
        )
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE credit_reservations SET expires_at=now() - interval '1 second' "
                "WHERE idempotency_key='crashed-operation'"
            )
        )
    with client.app.state.container.database.session_factory() as session:
        assert CreditLedgerService(session).reconcile_expired() == 1
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT ca.reserved_credits, cr.status "
                "FROM credit_accounts ca JOIN credit_reservations cr "
                "ON ca.tenant_id=cr.tenant_id WHERE cr.idempotency_key='crashed-operation'"
            )
        ).one()
    engine.dispose()
    assert state == (0, "released")


def test_expired_started_reservation_is_conservatively_charged(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    estimate = estimated_chat_charge("gpt-5.4-mini")
    with client.app.state.container.database.session_factory() as session:
        ledger = CreditLedgerService(session)
        ledger.reserve(
            UUID(tenant["id"]),
            resource="ai_message",
            model="gpt-5.4-mini",
            estimate=estimate,
            idempotency_key="crashed-after-provider-call",
            reference_id=None,
        )
        ledger.start_reservation(UUID(tenant["id"]), "crashed-after-provider-call")
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE credit_reservations SET expires_at=now() - interval '1 second' "
                "WHERE idempotency_key='crashed-after-provider-call'"
            )
        )
    with client.app.state.container.database.session_factory() as session:
        assert CreditLedgerService(session).reconcile_expired() == 1
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT cr.status, cl.delta_credits FROM credit_reservations cr "
                "JOIN credit_ledger cl ON cl.tenant_id=cr.tenant_id "
                "WHERE cr.idempotency_key='crashed-after-provider-call'"
            )
        ).one()
    engine.dispose()
    assert state == ("settled", -estimate.credits)


def test_late_completion_after_reconcile_cannot_double_settle_or_go_negative(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    tenant_id = UUID(tenant["id"])
    estimate = estimated_chat_charge("gpt-5.4-mini")
    with client.app.state.container.database.session_factory() as session:
        ledger = CreditLedgerService(session)
        ledger.reserve(
            tenant_id,
            resource="ai_message",
            model="gpt-5.4-mini",
            estimate=estimate,
            idempotency_key="late-completion",
            reference_id=None,
        )
        ledger.start_reservation(tenant_id, "late-completion")
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE credit_reservations SET expires_at=now() - interval '1 second' "
                "WHERE idempotency_key='late-completion'"
            )
        )
    with client.app.state.container.database.session_factory() as session:
        assert CreditLedgerService(session).reconcile_expired() == 1
    with client.app.state.container.database.session_factory() as session:
        with pytest.raises(CreditReservationClosed):
            CreditLedgerService(session).settle_reservation(
                tenant_id,
                idempotency_key="late-completion",
                model="gpt-5.4-mini",
                charge=chat_charge(
                    "gpt-5.4-mini",
                    input_tokens=10,
                    cached_input_tokens=0,
                    output_tokens=10,
                ),
                reference_id=None,
                extra={},
            )
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT ca.reserved_credits, count(cl.id) "
                "FROM credit_accounts ca JOIN credit_ledger cl "
                "ON ca.tenant_id=cl.tenant_id WHERE ca.tenant_id=:tenant_id "
                "GROUP BY ca.reserved_credits"
            ),
            {"tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert state == (0, 1)


def test_actual_overage_is_charged_atomically_after_provider_cost(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    tenant_id = UUID(tenant["id"])
    _account(
        migrated_database,
        tenant["id"],
        enforcement_mode="enforce",
        balance_credits=1,
    )
    estimate = CreditCharge(
        provider_cost_usd=chat_charge(
            "gpt-5.4-mini",
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=0,
        ).provider_cost_usd,
        retail_cost_usd=chat_charge(
            "gpt-5.4-mini",
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=0,
        ).retail_cost_usd,
        credits=1,
    )
    actual = CreditCharge(
        provider_cost_usd=estimate.provider_cost_usd,
        retail_cost_usd=estimate.retail_cost_usd,
        credits=5,
    )
    with client.app.state.container.database.session_factory() as session:
        ledger = CreditLedgerService(session)
        ledger.reserve(
            tenant_id,
            resource="ai_message",
            model="gpt-5.4-mini",
            estimate=estimate,
            idempotency_key="overage",
            reference_id=None,
        )
        ledger.start_reservation(tenant_id, "overage")
        ledger.settle_reservation(
            tenant_id,
            idempotency_key="overage",
            model="gpt-5.4-mini",
            charge=actual,
            reference_id=None,
            extra={"overage": True},
        )
        session.commit()
    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT balance_credits, reserved_credits FROM credit_accounts "
                "WHERE tenant_id=:tenant_id"
            ),
            {"tenant_id": tenant["id"]},
        ).one()
    engine.dispose()
    assert state == (-4, 0)


@pytest.mark.parametrize(
    ("snapshot_unlimited", "toggled_unlimited", "expected_delta"),
    [(True, False, 0), (False, True, -1)],
)
def test_settlement_uses_frozen_unlimited_snapshot(
    client: TestClient,
    migrated_database: str,
    snapshot_unlimited: bool,
    toggled_unlimited: bool,
    expected_delta: int,
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    tenant_id = UUID(tenant["id"])
    _account(
        migrated_database,
        tenant["id"],
        enforcement_mode="meter_only",
        balance_credits=0,
        unlimited_messages=snapshot_unlimited,
    )
    estimate = estimated_chat_charge("gpt-5.4-mini")
    with client.app.state.container.database.session_factory() as session:
        ledger = CreditLedgerService(session)
        reservation = ledger.reserve(
            tenant_id,
            resource="ai_message",
            model="gpt-5.4-mini",
            estimate=estimate,
            idempotency_key="snapshot-toggle",
            reference_id=None,
        )
        assert reservation.extra["unlimited_messages_snapshot"] is snapshot_unlimited
        ledger.start_reservation(tenant_id, "snapshot-toggle")
    _account(
        migrated_database,
        tenant["id"],
        unlimited_messages=toggled_unlimited,
    )
    with client.app.state.container.database.session_factory() as session:
        CreditLedgerService(session).settle_reservation(
            tenant_id,
            idempotency_key="snapshot-toggle",
            model="gpt-5.4-mini",
            charge=CreditCharge(
                provider_cost_usd=estimate.provider_cost_usd,
                retail_cost_usd=estimate.retail_cost_usd,
                credits=1,
            ),
            reference_id=None,
            extra={},
        )
        session.commit()
    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        delta = connection.scalar(
            text("SELECT delta_credits FROM credit_ledger WHERE tenant_id=:tenant_id"),
            {"tenant_id": tenant["id"]},
        )
    engine.dispose()
    assert delta == expected_delta
