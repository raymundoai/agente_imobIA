from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.modules.billing_usage.adapters.models import (
    CommercialEntitlementGrantModel,
    TenantCommercialSubscriptionModel,
)
from app.modules.billing_usage.asaas import asaas_webhook_token

pytestmark = pytest.mark.integration

SIGNUP = {
    "company_name": "Imobiliária Horizonte",
    "admin_name": "Ana Corretora",
    "email": "ana@horizonte.example.com",
    "password": "senha-forte-horizonte-1",
    "accept_terms": True,
}


class FakeAsaasClient:
    def __init__(self) -> None:
        self.created_subscriptions: list[dict] = []
        self.created_customers: list[dict] = []
        self.created_payments: list[dict] = []

    def find_customer(self, external_reference: str) -> dict | None:
        return None

    def create_customer(self, payload: dict) -> dict:
        self.created_customers.append(payload)
        return {"id": "cus_self"}

    def create_subscription(self, payload: dict) -> dict:
        self.created_subscriptions.append(payload)
        return {"id": "sub_self", "status": "ACTIVE"}

    def find_subscription(self, external_reference: str) -> dict | None:
        return None

    def find_payment(self, external_reference: str) -> dict | None:
        return None

    def create_payment(self, payload: dict) -> dict:
        self.created_payments.append(payload)
        return {"id": f"pay_pack_{len(self.created_payments)}", "invoiceUrl": "https://i/pack"}

    def subscription_payments(self, subscription_id: str) -> list[dict]:
        return [
            {
                "id": "pay_self",
                "status": "PENDING",
                "dueDate": "2026-10-02",
                "value": 369.0,
                "invoiceUrl": "https://sandbox.asaas.com/i/pay_self",
            }
        ]

    def pix_qr_code(self, payment_id: str) -> dict:
        assert payment_id == "pay_self"
        return {
            "encodedImage": "iVBORw0KGgo=",
            "payload": "00020101021226820014br.gov.bcb.pix",
            "expirationDate": "2026-10-02 23:59:59",
        }


@pytest.fixture
def signup_enabled(client: TestClient) -> TestClient:
    client.app.state.container.settings.public_signup_enabled = True
    client.app.state.container.settings.trial_days = 0
    return client


def _signup(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/signup", json={**SIGNUP, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def _auth(body: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {body['access_token']}"}


def _available(usage: dict[str, Any], resource: str) -> int:
    return next(item["available"] for item in usage["resources"] if item["resource"] == resource)


def test_signup_is_disabled_by_default(client: TestClient) -> None:
    from app.config import Settings

    assert Settings.model_fields["public_signup_enabled"].default is False
    client.app.state.container.settings.public_signup_enabled = False
    assert client.post("/signup", json=SIGNUP).status_code == 403


def test_signup_requires_accepting_the_terms(signup_enabled: TestClient) -> None:
    refused = signup_enabled.post("/signup", json={**SIGNUP, "accept_terms": False})
    assert refused.status_code == 422
    body = _signup(signup_enabled)
    tenant = signup_enabled.get(f"/tenants/{body['tenant_id']}", headers=_auth(body)).json()
    assert tenant["settings"]["legal"]["terms_version"] == "2026-10-05"
    assert tenant["settings"]["legal"]["accepted_by"] == SIGNUP["email"]


def test_signup_waits_for_first_subscription_without_allowance(
    signup_enabled: TestClient,
) -> None:
    body = _signup(signup_enabled)
    assert body["trial_ends_at"] is None
    usage = signup_enabled.get("/usage/commercial", headers=_auth(body)).json()
    assert usage["plan"]["code"] == "sem_plano"
    assert usage["status"] == "pending"
    assert usage["enforcement_mode"] == "enforce"
    assert _available(usage, "ai_attendance") == 0


def test_signup_starts_enforced_trial_and_pending_onboarding(signup_enabled: TestClient) -> None:
    client = signup_enabled
    client.app.state.container.settings.trial_days = 7
    body = _signup(client)
    assert body["tenant_slug"] == "imobiliaria-horizonte"
    trial_ends_at = datetime.fromisoformat(body["trial_ends_at"])
    assert timedelta(days=6, hours=23) < trial_ends_at - datetime.now(UTC) <= timedelta(days=7)

    usage = client.get("/usage/commercial", headers=_auth(body)).json()
    assert usage["plan"]["code"] == "teste_gratis"
    assert usage["status"] == "trial"
    assert usage["enforcement_mode"] == "enforce"
    assert _available(usage, "ai_attendance") == 30

    tenant = client.get(f"/tenants/{body['tenant_id']}", headers=_auth(body)).json()
    assert tenant["settings"]["onboarding"] == {"status": "pending"}
    done = client.patch(
        f"/tenants/{body['tenant_id']}/onboarding",
        headers=_auth(body),
        json={"status": "skipped"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["settings"]["onboarding"] == {"status": "skipped"}

    login = client.post(
        "/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert login.status_code == 200, login.text
    assert login.json()["tenant_slug"] == "imobiliaria-horizonte"


def test_signup_generates_unique_internal_slug_and_rejects_known_email(
    signup_enabled: TestClient,
) -> None:
    client = signup_enabled
    first = _signup(client)
    second = _signup(client, email="bruno@horizonte.example.com")
    assert first["tenant_slug"] == "imobiliaria-horizonte"
    assert second["tenant_slug"] == "imobiliaria-horizonte-2"
    assert _signup(client, company_name="Admin", email="c@example.com")["tenant_slug"] == "admin-2"

    duplicate = client.post("/signup", json={**SIGNUP, "company_name": "Outra"})
    assert duplicate.status_code == 409
    assert "já tem uma conta" in duplicate.json()["detail"]


def test_trial_allowance_ends_and_does_not_renew(signup_enabled: TestClient) -> None:
    client = signup_enabled
    client.app.state.container.settings.trial_days = 7
    body = _signup(client)
    tenant_id = UUID(body["tenant_id"])
    past = datetime.now(UTC) - timedelta(minutes=1)
    with client.app.state.container.database.session_factory() as session:
        session.execute(
            update(CommercialEntitlementGrantModel)
            .where(CommercialEntitlementGrantModel.tenant_id == tenant_id)
            .values(valid_from=past - timedelta(days=7), expires_at=past)
        )
        session.execute(
            update(TenantCommercialSubscriptionModel)
            .where(TenantCommercialSubscriptionModel.tenant_id == tenant_id)
            .values(cycle_started_at=past - timedelta(days=7), cycle_ends_at=past)
        )
        session.commit()

    usage = client.get("/usage/commercial", headers=_auth(body)).json()
    assert usage["status"] == "trial"
    assert _available(usage, "ai_attendance") == 0


def test_agency_subscribes_itself_and_payment_activates_plan(
    signup_enabled: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.billing_usage import api as billing_api

    client = signup_enabled
    fake = FakeAsaasClient()
    monkeypatch.setattr(billing_api, "asaas_client_from_settings", lambda *_: fake)
    body = _signup(client)

    overview = client.get("/billing", headers=_auth(body)).json()
    assert overview["status"] == "pending"
    assert overview["subscription"] is None
    assert overview["payments_enabled"] is True
    assert overview["contact"]["email"] == SIGNUP["email"]
    assert [plan["code"] for plan in overview["plans"]] == [
        "essencial",
        "profissional",
        "avancado",
        "escala",
    ]
    assert overview["packs"] == []

    subscribed = client.post(
        "/billing/subscription",
        headers=_auth(body),
        json={
            "plan_code": "essencial",
            "billing_type": "CREDIT_CARD",
            "idempotency_key": "self-service-horizonte-1",
            "customer": {
                "name": "Imobiliária Horizonte Ltda",
                "email": "financeiro@horizonte.example.com",
                "cpf_cnpj": "11.222.333/0001-81",
            },
        },
    )
    assert subscribed.status_code == 201, subscribed.text
    subscription = subscribed.json()["subscription"]
    assert subscription["status"] == "pending_payment"
    assert subscription["billing_type"] == "CREDIT_CARD"
    assert subscription["invoice_url"] == "https://sandbox.asaas.com/i/pay_self"
    assert fake.created_subscriptions[0]["billingType"] == "CREDIT_CARD"
    assert fake.created_customers[0]["notificationDisabled"] is False

    token = asaas_webhook_token(client.app.state.container.settings)
    confirmed = client.post(
        "/webhooks/asaas",
        headers={"asaas-access-token": token},
        json={
            "id": "evt_self_confirmed",
            "event": "PAYMENT_CONFIRMED",
            "payment": {"id": "pay_self", "subscription": "sub_self", "status": "CONFIRMED"},
        },
    )
    assert confirmed.json()["outcome"] == "activated"

    usage = client.get("/usage/commercial", headers=_auth(body)).json()
    assert usage["plan"]["code"] == "essencial"
    assert usage["status"] == "active"
    # Trial leftovers are replaced by the paid plan's allowance.
    assert _available(usage, "ai_attendance") == 100


def test_trial_plan_cannot_be_assigned_as_regular_plan(signup_enabled: TestClient) -> None:
    from tests.integration.test_asaas_billing import _platform_token

    client = signup_enabled
    body = _signup(client)
    response = client.put(
        f"/platform/tenants/{body['tenant_id']}/commercial-subscription",
        headers={"Authorization": f"Bearer {_platform_token(client)}"},
        json={"plan_code": "teste_gratis", "enforcement_mode": "enforce"},
    )
    assert response.status_code == 404


def _subscribe(client: TestClient, body: dict[str, Any], billing_type: str, key: str):
    return client.post(
        "/billing/subscription",
        headers=_auth(body),
        json={
            "plan_code": "essencial",
            "billing_type": billing_type,
            "idempotency_key": key,
            "customer": {
                "name": "Imobiliária Horizonte Ltda",
                "email": "financeiro@horizonte.example.com",
                "cpf_cnpj": "11.222.333/0001-81",
            },
        },
    )


def test_pix_qr_code_is_served_inside_the_app(
    signup_enabled: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.billing_usage import api as billing_api

    client = signup_enabled
    monkeypatch.setattr(billing_api, "asaas_client_from_settings", lambda *_: FakeAsaasClient())
    body = _signup(client)
    assert client.get("/billing/pix", headers=_auth(body)).status_code == 404

    assert _subscribe(client, body, "PIX", "self-service-pix-1").status_code == 201
    pix = client.get("/billing/pix", headers=_auth(body))
    assert pix.status_code == 200, pix.text
    assert pix.json() == {
        "payment_id": "pay_self",
        "value_cents": 36900,
        "due_date": "2026-10-02",
        "payload": "00020101021226820014br.gov.bcb.pix",
        "encoded_image": "iVBORw0KGgo=",
        "expiration_date": "2026-10-02T23:59:59",
    }


def test_pix_qr_code_is_refused_for_card_subscription(
    signup_enabled: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.billing_usage import api as billing_api

    client = signup_enabled
    monkeypatch.setattr(billing_api, "asaas_client_from_settings", lambda *_: FakeAsaasClient())
    body = _signup(client)
    assert _subscribe(client, body, "CREDIT_CARD", "self-service-card-1").status_code == 201
    assert client.get("/billing/pix", headers=_auth(body)).status_code == 409


def _confirm(client: TestClient, event_id: str, payment: dict[str, Any]) -> dict[str, Any]:
    token = asaas_webhook_token(client.app.state.container.settings)
    response = client.post(
        "/webhooks/asaas",
        headers={"asaas-access-token": token},
        json={"id": event_id, "event": "PAYMENT_RECEIVED", "payment": payment},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _platform(client: TestClient) -> dict[str, str]:
    from tests.integration.test_asaas_billing import _platform_token

    return {"Authorization": f"Bearer {_platform_token(client)}"}


def test_beta_tenant_sees_and_pays_the_beta_price(
    signup_enabled: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.billing_usage import api as billing_api

    client = signup_enabled
    fake = FakeAsaasClient()
    monkeypatch.setattr(billing_api, "asaas_client_from_settings", lambda *_: fake)
    body = _signup(client)
    platform = _platform(client)

    marked = client.patch(
        f"/platform/tenants/{body['tenant_id']}/beta", headers=platform, json={"beta_pricing": True}
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["beta_pricing"] is True

    plans = {
        plan["code"]: plan for plan in client.get("/billing", headers=_auth(body)).json()["plans"]
    }
    assert plans["essencial"]["monthly_price_cents"] == 4900
    assert plans["essencial"]["list_price_cents"] == 36900

    changed = client.patch(
        "/platform/commercial/plans/essencial/beta-price",
        headers=platform,
        json={"beta_price_cents": 5900},
    )
    assert changed.json()["beta_price_cents"] == 5900
    assert _subscribe(client, body, "PIX", "beta-pix-1").status_code == 201
    assert fake.created_subscriptions[0]["value"] == 59.0


def test_pack_is_bought_and_credited_when_paid(
    signup_enabled: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.billing_usage import api as billing_api

    client = signup_enabled
    fake = FakeAsaasClient()
    monkeypatch.setattr(billing_api, "asaas_client_from_settings", lambda *_: fake)
    body = _signup(client)
    order_payload = {"resource": "ai_attendance", "idempotency_key": "pack-order-1"}

    early = client.post("/billing/packs", headers=_auth(body), json=order_payload)
    assert early.status_code == 409
    assert "Assine um plano" in early.json()["detail"]

    assert _subscribe(client, body, "PIX", "pack-sub-1").status_code == 201
    _confirm(client, "evt_sub_paid", {"id": "pay_self", "subscription": "sub_self"})
    overview = client.get("/billing", headers=_auth(body)).json()
    offers = {pack["resource"]: pack for pack in overview["packs"]}
    # 50 × R$ 2,00 × 1,15 = R$ 115; 20 photos × R$ 2,50 × 1,15 = R$ 57,50 → R$ 58.
    assert offers["ai_attendance"] == {
        "resource": "ai_attendance",
        "units": 50,
        "price_cents": 11500,
    }
    assert offers["image_optimization"]["price_cents"] == 5800

    created = client.post("/billing/packs", headers=_auth(body), json=order_payload)
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["status"] == "pending_payment"
    assert fake.created_payments[0]["value"] == 115.0
    again = client.post("/billing/packs", headers=_auth(body), json=order_payload)
    assert again.json()["id"] == order["id"]
    assert len(fake.created_payments) == 1

    before = _available(
        client.get("/usage/commercial", headers=_auth(body)).json(), "ai_attendance"
    )
    reference = f"immobia:pack:{order['id']}"
    result = _confirm(client, "evt_pack_paid", {"id": "pay_pack_1", "externalReference": reference})
    assert result["outcome"] == "pack_granted"
    after = _available(client.get("/usage/commercial", headers=_auth(body)).json(), "ai_attendance")
    assert after == before + 50
    repeat = _confirm(
        client, "evt_pack_paid_again", {"id": "pay_pack_1", "externalReference": reference}
    )
    assert repeat["outcome"] == "pack_already_paid"


def test_internal_test_account_is_unlimited_and_offered_only_the_test_plan(
    signup_enabled: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.billing_usage import api as billing_api

    client = signup_enabled
    fake = FakeAsaasClient()
    monkeypatch.setattr(billing_api, "asaas_client_from_settings", lambda *_: fake)
    customer = _signup(client, email="cliente@horizonte.example.com")
    body = _signup(client)
    platform = _platform(client)

    # Regular customers never see nor buy the private test plan.
    regular = client.get("/billing", headers=_auth(customer)).json()
    assert "teste_pagamento" not in [plan["code"] for plan in regular["plans"]]
    refused = client.post(
        "/billing/subscription",
        headers=_auth(customer),
        json={
            "plan_code": "teste_pagamento",
            "billing_type": "PIX",
            "idempotency_key": "regular-test-plan",
            "customer": {
                "name": "Cliente",
                "email": "cliente@horizonte.example.com",
                "cpf_cnpj": "11.222.333/0001-81",
            },
        },
    )
    assert refused.status_code == 409

    marked = client.patch(
        f"/platform/tenants/{body['tenant_id']}/internal-test",
        headers=platform,
        json={"internal_test": True},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["internal_test"] is True
    assert marked.json()["commercial_enforcement"] == "meter_only"

    overview = client.get("/billing", headers=_auth(body)).json()
    assert overview["internal_test"] is True
    assert [plan["code"] for plan in overview["plans"]] == ["teste_pagamento"]
    assert overview["plans"][0]["monthly_price_cents"] == 500
    assert _subscribe(client, body, "PIX", "internal-essencial").status_code == 409

    subscribed = client.post(
        "/billing/subscription",
        headers=_auth(body),
        json={
            "plan_code": "teste_pagamento",
            "billing_type": "PIX",
            "idempotency_key": "internal-test-plan",
            "customer": {
                "name": "Imobiliária Horizonte Ltda",
                "email": "financeiro@horizonte.example.com",
                "cpf_cnpj": "11.222.333/0001-81",
            },
        },
    )
    assert subscribed.status_code == 201, subscribed.text
    assert fake.created_subscriptions[0]["value"] == 5.0

    token = asaas_webhook_token(client.app.state.container.settings)
    confirmed = client.post(
        "/webhooks/asaas",
        headers={"asaas-access-token": token},
        json={
            "id": "evt_internal_confirmed",
            "event": "PAYMENT_CONFIRMED",
            "payment": {"id": "pay_self", "subscription": "sub_self", "status": "CONFIRMED"},
        },
    )
    assert confirmed.json()["outcome"] == "activated"
    summary = client.get(f"/platform/tenants/{body['tenant_id']}", headers=platform).json()
    assert summary["commercial_plan"] == "teste_pagamento"
    assert summary["commercial_status"] == "active"
    # Paying the test plan keeps the account unlimited.
    assert summary["commercial_enforcement"] == "meter_only"

    unmarked = client.patch(
        f"/platform/tenants/{body['tenant_id']}/internal-test",
        headers=platform,
        json={"internal_test": False},
    )
    assert unmarked.json()["internal_test"] is False
    assert unmarked.json()["commercial_enforcement"] == "enforce"
