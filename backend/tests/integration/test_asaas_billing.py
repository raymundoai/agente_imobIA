from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.modules.billing_usage.asaas import AsaasAmbiguousError, asaas_webhook_token
from app.shared.errors.exceptions import ExternalServiceError
from tests.conftest import TEST_PLATFORM_BOOTSTRAP_TOKEN
from tests.integration.test_whatsapp_webhook_idempotency import _provision

pytestmark = pytest.mark.integration


class FakeAsaasClient:
    def __init__(self) -> None:
        self.created_webhook_payloads: list[dict] = []
        self.updated_webhook_payloads: list[tuple[str, dict]] = []
        self.created_subscriptions: list[dict] = []
        self.remote_subscriptions: dict[str, dict] = {}
        self.deleted_subscriptions: list[str] = []
        # Each item is raised by one create_subscription call; "lost" means Asaas created
        # the subscription but the response never arrived.
        self.create_failures: list[Exception | str] = []

    def account(self) -> dict:
        return {"id": "acc_sandbox", "name": "Conta Sandbox"}

    def find_customer(self, external_reference: str) -> dict | None:
        assert external_reference.startswith("immobia:tenant:")
        return None

    def create_customer(self, payload: dict) -> dict:
        assert payload["externalReference"].startswith("immobia:tenant:")
        return {"id": "cus_sandbox"}

    def create_subscription(self, payload: dict) -> dict:
        assert payload["customer"] == "cus_sandbox"
        assert payload["billingType"] == "PIX"
        assert payload["cycle"] == "MONTHLY"
        assert payload["value"] == 399.0
        failure = self.create_failures.pop(0) if self.create_failures else None
        if isinstance(failure, Exception):
            raise failure
        self.created_subscriptions.append(payload)
        remote = {
            "id": f"sub_sandbox_{len(self.created_subscriptions)}",
            "status": "ACTIVE",
            "externalReference": payload["externalReference"],
        }
        self.remote_subscriptions[payload["externalReference"]] = remote
        if failure == "lost":
            raise AsaasAmbiguousError("timeout")
        return remote

    def find_subscription(self, external_reference: str) -> dict | None:
        return self.remote_subscriptions.get(external_reference)

    def delete_subscription(self, subscription_id: str) -> dict:
        self.deleted_subscriptions.append(subscription_id)
        return {"deleted": True, "id": subscription_id}

    def subscription_payments(self, subscription_id: str) -> list[dict]:
        return [
            {
                "id": f"pay_{subscription_id}",
                "invoiceUrl": f"https://sandbox.asaas.com/i/pay_{subscription_id}",
            }
        ]

    def create_webhook(self, payload: dict) -> dict:
        self.created_webhook_payloads.append(payload)
        return {"id": "webhook_sandbox"}

    def update_webhook(self, webhook_id: str, payload: dict) -> dict:
        self.updated_webhook_payloads.append((webhook_id, payload))
        return {"id": webhook_id}


@pytest.fixture
def fake_asaas(monkeypatch: pytest.MonkeyPatch) -> FakeAsaasClient:
    from app.modules.billing_usage import api as billing_api
    from app.modules.platform import api as platform_api

    fake = FakeAsaasClient()
    monkeypatch.setattr(platform_api, "asaas_client_from_settings", lambda *_: fake)
    monkeypatch.setattr(billing_api, "asaas_client_from_settings", lambda *_: fake)
    return fake


def _platform_token(client: TestClient) -> str:
    response = client.post(
        "/platform/auth/bootstrap",
        headers={"X-Platform-Bootstrap-Token": TEST_PLATFORM_BOOTSTRAP_TOKEN},
        json={
            "name": "Dono da Plataforma",
            "email": "billing@example.com",
            "password": "strong-platform-password-123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _setup(client: TestClient) -> tuple[dict, dict, dict]:
    platform_auth = {"Authorization": f"Bearer {_platform_token(client)}"}
    tenant, tenant_token = _provision(client, "tenant-a")
    return tenant, platform_auth, {"Authorization": f"Bearer {tenant_token}"}


def _create(client: TestClient, tenant: dict, auth: dict, key: str = "asaas-key-tenant-a"):
    due_date = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    return client.post(
        f"/platform/tenants/{tenant['id']}/asaas/subscriptions",
        headers=auth,
        json={
            "plan_code": "ia_essencial",
            "billing_type": "PIX",
            "next_due_date": due_date,
            "enforcement_mode": "enforce",
            "idempotency_key": key,
            "customer": {
                "name": "Imobiliária Teste",
                "email": "financeiro@example.com",
                "cpf_cnpj": "12.345.678/0001-90",
            },
        },
    )


def _event(client: TestClient, event_id: str, event: str, provider_id: str) -> dict[str, Any]:
    token = asaas_webhook_token(client.app.state.container.settings)
    if event.startswith("SUBSCRIPTION_"):
        body: dict[str, Any] = {"id": event_id, "event": event, "subscription": {"id": provider_id}}
    else:
        body = {
            "id": event_id,
            "event": event,
            "payment": {"id": f"pay_{event_id}", "subscription": provider_id, "status": event},
        }
    response = client.post("/webhooks/asaas", headers={"asaas-access-token": token}, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _commercial(client: TestClient, tenant_auth: dict) -> dict[str, Any]:
    response = client.get("/usage/commercial", headers=tenant_auth)
    assert response.status_code == 200, response.text
    return response.json()


def _available(usage: dict[str, Any], resource: str = "ai_attendance") -> int:
    return next(item["available"] for item in usage["resources"] if item["resource"] == resource)


def test_asaas_subscription_activates_commercial_plan_from_webhook(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, tenant_auth = _setup(client)

    created = _create(client, tenant, platform_auth)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending_payment"
    assert created.json()["provider_subscription_id"] == "sub_sandbox_1"
    assert created.json()["invoice_url"] == "https://sandbox.asaas.com/i/pay_sub_sandbox_1"
    assert _commercial(client, tenant_auth)["plan"]["code"] == "piloto_mvp"

    assert _event(client, "evt_confirmed", "PAYMENT_CONFIRMED", "sub_sandbox_1") == {
        "received": True,
        "duplicate": False,
        "outcome": "activated",
    }
    assert _event(client, "evt_confirmed", "PAYMENT_CONFIRMED", "sub_sandbox_1")["duplicate"]

    after = _commercial(client, tenant_auth)
    assert after["plan"]["code"] == "ia_essencial"
    assert after["status"] == "active"
    assert after["enforcement_mode"] == "enforce"


def test_second_open_subscription_is_refused(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, _ = _setup(client)
    assert _create(client, tenant, platform_auth).status_code == 201

    same_key = _create(client, tenant, platform_auth)
    assert same_key.status_code == 201
    assert same_key.json()["provider_subscription_id"] == "sub_sandbox_1"

    other_key = _create(client, tenant, platform_auth, key="asaas-key-tenant-a-2")
    assert other_key.status_code == 409, other_key.text
    assert len(fake_asaas.created_subscriptions) == 1


def test_overdue_suspends_renewal_and_payment_reactivates(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, tenant_auth = _setup(client)
    _create(client, tenant, platform_auth)
    _event(client, "evt_confirmed", "PAYMENT_CONFIRMED", "sub_sandbox_1")
    granted = _available(_commercial(client, tenant_auth))
    assert granted > 0

    overdue = _event(client, "evt_overdue", "PAYMENT_OVERDUE", "sub_sandbox_1")
    assert overdue["outcome"] == "past_due_suspended"
    usage = _commercial(client, tenant_auth)
    assert usage["status"] == "past_due"
    # Grace period: what is left of the current cycle is kept; only renewal stops.
    assert _available(usage) == granted

    reactivated = _event(client, "evt_received", "PAYMENT_RECEIVED", "sub_sandbox_1")
    assert reactivated["outcome"] == "activated"
    usage = _commercial(client, tenant_auth)
    assert usage["status"] == "active"
    assert _available(usage) == granted


def test_overdue_before_first_payment_keeps_tenant_on_pilot(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, tenant_auth = _setup(client)
    _create(client, tenant, platform_auth)

    overdue = _event(client, "evt_overdue", "PAYMENT_OVERDUE", "sub_sandbox_1")
    assert overdue["outcome"] == "past_due_recorded"
    usage = _commercial(client, tenant_auth)
    assert usage["plan"]["code"] == "piloto_mvp"
    assert usage["status"] == "pilot"


def test_subscription_deleted_in_asaas_revokes_plan(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, tenant_auth = _setup(client)
    _create(client, tenant, platform_auth)
    _event(client, "evt_confirmed", "PAYMENT_CONFIRMED", "sub_sandbox_1")

    deleted = _event(client, "evt_deleted", "SUBSCRIPTION_DELETED", "sub_sandbox_1")
    assert deleted["outcome"] == "cancelled_recorded"
    usage = _commercial(client, tenant_auth)
    assert usage["status"] == "cancelled"
    assert _available(usage) == 0

    late = _event(client, "evt_late", "PAYMENT_RECEIVED", "sub_sandbox_1")
    assert late["outcome"] == "ignored_inactive_subscription"
    assert _commercial(client, tenant_auth)["status"] == "cancelled"


def test_platform_cancel_deletes_in_asaas_and_allows_new_subscription(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, tenant_auth = _setup(client)
    subscription_id = _create(client, tenant, platform_auth).json()["id"]
    _event(client, "evt_confirmed", "PAYMENT_CONFIRMED", "sub_sandbox_1")

    cancelled = client.post(
        f"/platform/tenants/{tenant['id']}/asaas/subscriptions/{subscription_id}/cancel",
        headers=platform_auth,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert fake_asaas.deleted_subscriptions == ["sub_sandbox_1"]
    assert _commercial(client, tenant_auth)["status"] == "cancelled"

    # The SUBSCRIPTION_DELETED that Asaas sends afterwards changes nothing.
    echo = _event(client, "evt_deleted", "SUBSCRIPTION_DELETED", "sub_sandbox_1")
    assert echo["outcome"] == "already_cancelled"

    replacement = _create(client, tenant, platform_auth, key="asaas-key-tenant-a-2")
    assert replacement.status_code == 201, replacement.text

    listed = client.get(
        f"/platform/tenants/{tenant['id']}/asaas/subscriptions", headers=platform_auth
    )
    assert [item["status"] for item in listed.json()] == ["pending_payment", "cancelled"]


def test_lost_creation_response_is_reconciled_without_duplicate(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, _ = _setup(client)
    fake_asaas.create_failures = ["lost"]

    created = _create(client, tenant, platform_auth)
    # The lookup by externalReference right after the timeout finds the subscription.
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending_payment"
    assert len(fake_asaas.created_subscriptions) == 1


def test_unconfirmed_creation_stays_open_until_reconciled(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, _ = _setup(client)
    fake_asaas.create_failures = [AsaasAmbiguousError("timeout")]

    failed = _create(client, tenant, platform_auth)
    assert failed.status_code == 502, failed.text
    listed = client.get(
        f"/platform/tenants/{tenant['id']}/asaas/subscriptions", headers=platform_auth
    ).json()
    assert listed[0]["status"] == "creating"
    assert "timeout" in listed[0]["last_error"]

    blocked = _create(client, tenant, platform_auth, key="asaas-key-tenant-a-2")
    assert blocked.status_code == 409

    reconciled = client.post(
        f"/platform/tenants/{tenant['id']}/asaas/subscriptions/{listed[0]['id']}/reconcile",
        headers=platform_auth,
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["status"] == "pending_payment"
    assert reconciled.json()["last_error"] is None
    assert len(fake_asaas.created_subscriptions) == 1


def test_rejected_creation_is_failed_and_does_not_block(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    tenant, platform_auth, _ = _setup(client)
    fake_asaas.create_failures = [ExternalServiceError("Asaas retornou status 400: CPF inválido")]

    rejected = _create(client, tenant, platform_auth)
    assert rejected.status_code == 502
    retried_same_key = _create(client, tenant, platform_auth)
    assert retried_same_key.status_code == 409
    assert "CPF inválido" in retried_same_key.json()["detail"]

    new_key = _create(client, tenant, platform_auth, key="asaas-key-tenant-a-2")
    assert new_key.status_code == 201, new_key.text


def test_asaas_webhook_provisioning_and_authentication(
    client: TestClient, fake_asaas: FakeAsaasClient
) -> None:
    auth = {"Authorization": f"Bearer {_platform_token(client)}"}

    configured = client.post(
        "/platform/asaas/webhook",
        headers=auth,
        json={"notification_email": "billing@example.com"},
    )
    assert configured.status_code == 201, configured.text
    assert configured.json()["url"].endswith("/webhooks/asaas")
    payload = fake_asaas.created_webhook_payloads[0]
    assert payload["authToken"] != "test-asaas-api-key"
    assert "SUBSCRIPTION_DELETED" in payload["events"]

    updated = client.post(
        "/platform/asaas/webhook",
        headers=auth,
        json={"notification_email": "billing@example.com"},
    )
    assert updated.status_code == 201, updated.text
    assert fake_asaas.updated_webhook_payloads[0][0] == "webhook_sandbox"

    status = client.get("/platform/asaas/status", headers=auth).json()
    assert status["webhook_notification_email"] == "billing@example.com"
    assert status["webhook_url"] == status["expected_webhook_url"]
    assert status["webhook_url"].endswith("/webhooks/asaas")

    rejected = client.post("/webhooks/asaas", headers={"asaas-access-token": "invalid"}, json={})
    assert rejected.status_code == 401


def test_dedicated_webhook_token_overrides_derived_one(client: TestClient) -> None:
    settings = client.app.state.container.settings
    dedicated = settings.model_copy(update={"asaas_webhook_token": SecretStr("t" * 40)})
    assert asaas_webhook_token(dedicated) == "t" * 40
    assert asaas_webhook_token(settings) != "t" * 40
