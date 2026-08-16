from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.billing_usage.adapters.models import AiAttendanceSessionModel
from app.modules.billing_usage.commercial import (
    AI_ATTENDANCE,
    PROPERTY_SEARCH_STANDARD,
    AiAttendanceService,
    CommercialAllowanceExhausted,
    CommercialEntitlementService,
)
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.messaging.processor import MessageJobProcessor
from tests.conftest import TEST_PLATFORM_BOOTSTRAP_TOKEN, TEST_WEBHOOK_SECRET
from tests.integration.test_message_job_resilience import CountingChannel
from tests.integration.test_whatsapp_webhook_idempotency import (
    FakeAutoReplyAi,
    _payload,
    _provision,
)

pytestmark = pytest.mark.integration


class DeliveringChannel(CountingChannel):
    def __init__(self, inbound_delegate: MessageChannelPort) -> None:
        super().__init__()
        self._inbound_delegate = inbound_delegate

    def receive_message(self, payload):
        return self._inbound_delegate.receive_message(payload)


def _platform_token(client: TestClient) -> str:
    response = client.post(
        "/platform/auth/bootstrap",
        headers={"X-Platform-Bootstrap-Token": TEST_PLATFORM_BOOTSTRAP_TOKEN},
        json={
            "name": "Dono da Plataforma",
            "email": "commercial@example.com",
            "password": "strong-platform-password-123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _assign_operation_plan(client: TestClient, token: str, tenant_id: str) -> None:
    response = client.put(
        f"/platform/tenants/{tenant_id}/commercial-subscription",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_code": "operacao", "enforcement_mode": "enforce"},
    )
    assert response.status_code == 200, response.text


def test_commercial_api_exposes_pilot_and_platform_can_assign_and_grant(
    client: TestClient,
) -> None:
    platform_token = _platform_token(client)
    tenant, tenant_token = _provision(client, "tenant-a")
    tenant_id = tenant["id"]
    tenant_auth = {"Authorization": f"Bearer {tenant_token}"}
    platform_auth = {"Authorization": f"Bearer {platform_token}"}

    pilot = client.get("/usage/commercial", headers=tenant_auth)
    assert pilot.status_code == 200, pilot.text
    assert pilot.json()["plan"]["code"] == "piloto_mvp"
    assert pilot.json()["enforcement_mode"] == "meter_only"
    assert {item["resource"]: item["available"] for item in pilot.json()["resources"]}[
        AI_ATTENDANCE
    ] == 300

    _assign_operation_plan(client, platform_token, tenant_id)
    assigned = client.get("/usage/commercial", headers=tenant_auth).json()
    resources = {item["resource"]: item for item in assigned["resources"]}
    assert assigned["plan"]["code"] == "operacao"
    assert assigned["enforcement_mode"] == "enforce"
    assert resources[AI_ATTENDANCE]["available"] == 0
    assert resources[PROPERTY_SEARCH_STANDARD]["available"] == 25
    _assign_operation_plan(client, platform_token, tenant_id)
    reassigned = client.get("/usage/commercial", headers=tenant_auth).json()
    assert {item["resource"]: item["available"] for item in reassigned["resources"]}[
        PROPERTY_SEARCH_STANDARD
    ] == 25

    grant = client.post(
        f"/platform/tenants/{tenant_id}/commercial-grants",
        headers=platform_auth,
        json={
            "resource": AI_ATTENDANCE,
            "quantity": 2,
            "source": "manual",
            "reference": "piloto assistido",
            "idempotency_key": "commercial-test-grant",
        },
    )
    repeated = client.post(
        f"/platform/tenants/{tenant_id}/commercial-grants",
        headers=platform_auth,
        json={
            "resource": AI_ATTENDANCE,
            "quantity": 2,
            "source": "manual",
            "reference": "piloto assistido",
            "idempotency_key": "commercial-test-grant",
        },
    )
    assert grant.status_code == 201, grant.text
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["id"] == grant.json()["id"]
    after = client.get("/usage/commercial", headers=tenant_auth).json()
    assert {item["resource"]: item["available"] for item in after["resources"]}[AI_ATTENDANCE] == 2

    for index in (1, 2):
        created_user = client.post(
            "/users",
            headers=tenant_auth,
            json={
                "name": f"Corretor {index}",
                "email": f"corretor{index}@example.com",
                "password": "strong-user-password-123",
                "role": "corretor",
            },
        )
        assert created_user.status_code == 201, created_user.text
    over_capacity = client.post(
        "/users",
        headers=tenant_auth,
        json={
            "name": "Corretor excedente",
            "email": "excedente@example.com",
            "password": "strong-user-password-123",
            "role": "corretor",
        },
    )
    assert over_capacity.status_code == 409
    assert "até 3 usuários" in over_capacity.text


def test_ai_attendance_charges_once_for_fixed_24_hour_window(
    client: TestClient, migrated_database: str
) -> None:
    platform_token = _platform_token(client)
    tenant, _ = _provision(client, "tenant-a")
    tenant_id = UUID(tenant["id"])
    _assign_operation_plan(client, platform_token, str(tenant_id))
    platform_auth = {"Authorization": f"Bearer {platform_token}"}
    grant = client.post(
        f"/platform/tenants/{tenant_id}/commercial-grants",
        headers=platform_auth,
        json={
            "resource": AI_ATTENDANCE,
            "quantity": 2,
            "source": "manual",
            "idempotency_key": "two-ai-attendances",
        },
    )
    assert grant.status_code == 201, grant.text

    engine = create_engine(migrated_database)
    contact_id = uuid4()
    conversation_id = uuid4()
    first_job = uuid4()
    with Session(engine) as session:
        attendance = AiAttendanceService(session)
        first = attendance.prepare(
            tenant_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
            phone="5511999999999",
            channel="whatsapp",
            opening_job_id=first_job,
            max_responses=50,
        )
        assert first.is_new_attendance is True
        attendance.settle_delivery(
            tenant_id, first.session_id, delivery_id=first_job, window_hours=24
        )

    second_job = uuid4()
    with Session(engine) as session:
        attendance = AiAttendanceService(session)
        second = attendance.prepare(
            tenant_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
            phone="5511999999999",
            channel="whatsapp",
            opening_job_id=second_job,
            max_responses=50,
        )
        assert second.session_id == first.session_id
        assert second.is_new_attendance is False
        attendance.settle_delivery(
            tenant_id, second.session_id, delivery_id=second_job, window_hours=24
        )
        summary = CommercialEntitlementService(session).resource_summary(tenant_id)
        assert summary[AI_ATTENDANCE]["consumed"] == 1
        assert summary[AI_ATTENDANCE]["measured"] == 1
        assert summary[AI_ATTENDANCE]["available"] == 1
        current = session.get(AiAttendanceSessionModel, first.session_id)
        assert current is not None and current.response_count == 2
        with pytest.raises(CommercialAllowanceExhausted):
            attendance.prepare(
                tenant_id,
                conversation_id=conversation_id,
                contact_id=contact_id,
                phone="5511999999999",
                channel="whatsapp",
                opening_job_id=uuid4(),
                max_responses=2,
            )

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE ai_attendance_sessions SET expires_at=:expired WHERE id=:attendance_id"),
            {
                "expired": datetime.now(UTC) - timedelta(seconds=1),
                "attendance_id": first.session_id,
            },
        )
    third_job = uuid4()
    with Session(engine) as session:
        attendance = AiAttendanceService(session)
        third = attendance.prepare(
            tenant_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
            phone="5511999999999",
            channel="whatsapp",
            opening_job_id=third_job,
            max_responses=50,
        )
        assert third.session_id != first.session_id
        attendance.settle_delivery(
            tenant_id, third.session_id, delivery_id=third_job, window_hours=24
        )
        summary = CommercialEntitlementService(session).resource_summary(tenant_id)
        assert summary[AI_ATTENDANCE]["consumed"] == 2
        assert summary[AI_ATTENDANCE]["measured"] == 2
        assert summary[AI_ATTENDANCE]["available"] == 0
        with pytest.raises(CommercialAllowanceExhausted):
            attendance.prepare(
                tenant_id,
                conversation_id=uuid4(),
                contact_id=uuid4(),
                phone="5511888888888",
                channel="whatsapp",
                opening_job_id=uuid4(),
                max_responses=50,
            )
    engine.dispose()


def test_meter_only_records_overage_and_release_does_not_consume(
    client: TestClient, migrated_database: str
) -> None:
    tenant, _ = _provision(client, "tenant-a")
    tenant_id = UUID(tenant["id"])
    engine = create_engine(migrated_database)
    with Session(engine) as session:
        service = CommercialEntitlementService(session)
        service.assign_plan(tenant_id, plan_code="operacao", enforcement_mode="meter_only")
        reserved = service.reserve(
            tenant_id,
            resource=AI_ATTENDANCE,
            idempotency_key="meter-only-ai",
            reference_id=uuid4(),
        )
        assert reserved.grant_id is None
        service.settle(tenant_id, "meter-only-ai")
        service.reserve(
            tenant_id,
            resource=PROPERTY_SEARCH_STANDARD,
            idempotency_key="released-search",
            reference_id=uuid4(),
        )
        service.release(tenant_id, "released-search")
        summary = service.resource_summary(tenant_id)
        assert summary[AI_ATTENDANCE]["measured"] == 1
        assert summary[AI_ATTENDANCE]["overage"] == 1
        assert summary[PROPERTY_SEARCH_STANDARD]["consumed"] == 0
        assert summary[PROPERTY_SEARCH_STANDARD]["available"] == 25
    engine.dispose()


def test_exhausted_ai_hands_conversation_to_team_without_calling_provider(
    client: TestClient, migrated_database: str
) -> None:
    platform_token = _platform_token(client)
    tenant, token = _provision(client, "tenant-a")
    _assign_operation_plan(client, platform_token, tenant["id"])
    client.app.state.container.ai_provider = FakeAutoReplyAi()
    client.app.state.container.settings.ai_auto_reply_enabled = True
    client.app.state.container.settings.ai_auto_send_to_channel = True

    inbound = client.post(
        "/webhooks/whatsapp/tenant-a",
        headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
        json=_payload("commercial-exhaustion"),
    )
    assert inbound.status_code == 200, inbound.text
    processed = MessageJobProcessor(client.app.state.container, "commercial-worker").process_next()
    assert processed is not None
    assert processed["status"] == "sent"
    assert processed["skipped"] == "commercial_allowance_exhausted"

    detail = client.get(
        f"/conversations/{inbound.json()['conversation_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["mode"] == "human"
    assert detail.json()["status"] == "waiting_human"
    assert [item["author_type"] for item in detail.json()["messages"]] == [
        "customer",
        "system",
    ]
    engine = create_engine(migrated_database)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM ai_audit_logs WHERE tenant_id=:tenant_id"),
                {"tenant_id": tenant["id"]},
            )
            == 0
        )
    engine.dispose()


def test_confirmed_ai_deliveries_reuse_the_same_commercial_attendance(
    client: TestClient,
) -> None:
    _, token = _provision(client, "tenant-a")
    client.app.state.container.ai_provider = FakeAutoReplyAi()
    client.app.state.container.message_channel = DeliveringChannel(
        client.app.state.container.message_channel
    )
    client.app.state.container.settings.ai_auto_reply_enabled = True
    client.app.state.container.settings.ai_auto_send_to_channel = True
    auth = {"Authorization": f"Bearer {token}"}

    for external_id in ("commercial-delivery-1", "commercial-delivery-2"):
        inbound = client.post(
            "/webhooks/whatsapp/tenant-a",
            headers={"X-ImobIA-Webhook-Secret": TEST_WEBHOOK_SECRET},
            json=_payload(external_id),
        )
        assert inbound.status_code == 200, inbound.text
        generated = MessageJobProcessor(
            client.app.state.container, f"generate-{external_id}"
        ).process_next()
        assert generated is not None and generated["status"] == "delivery_pending"
        delivered = MessageJobProcessor(
            client.app.state.container, f"deliver-{external_id}"
        ).process_next()
        assert delivered is not None and delivered["status"] == "sent"

    usage = client.get("/usage/commercial", headers=auth)
    assert usage.status_code == 200, usage.text
    attendance = next(
        item for item in usage.json()["resources"] if item["resource"] == AI_ATTENDANCE
    )
    assert attendance["measured"] == 1
    assert attendance["consumed"] == 1
    assert attendance["available"] == 299
    assert usage.json()["active_ai_attendances"] == 1
