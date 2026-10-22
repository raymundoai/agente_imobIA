"""Three manual broker test slots with enforced allowances and paid conversion."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.modules.billing_usage.adapters.models import (
    CommercialEntitlementGrantModel,
    TenantCommercialSubscriptionModel,
)
from app.modules.billing_usage.commercial import (
    CommercialAllowanceExhausted,
    CommercialEntitlementService,
)
from tests.integration.test_signup_billing import FakeAsaasClient, _confirm
from tests.integration.test_signup_invitations import _auth, _create, _signup

pytestmark = pytest.mark.integration


def test_three_invited_brokers_get_15_day_test_and_can_convert_to_paid(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.billing_usage import api as billing_api

    client.app.state.container.settings.public_signup_enabled = True
    platform = _auth(client)
    assert client.get("/platform/broker-test-access").status_code == 401
    assert (
        client.post("/platform/broker-test-access", json={"email": "a@example.com"}).status_code
        == 401
    )
    assert (
        client.post(
            "/platform/broker-test-access", headers=platform, json={"email": "missing@example.com"}
        ).status_code
        == 404
    )

    accounts = []
    for number in range(3):
        email = f"broker{number}@example.com"
        invitation = _create(client, platform)
        signed_up = client.post(
            "/signup",
            json=_signup(invitation["code"], email=email, company_name=f"Broker {number}"),
        )
        assert signed_up.status_code == 201, signed_up.text
        body = signed_up.json()
        accounts.append((email, body))
        granted = client.post(
            "/platform/broker-test-access", headers=platform, json={"email": email.upper()}
        )
        assert granted.status_code == 200, granted.text
        assert granted.json()["commercial_status"] == "trial"
        assert granted.json()["commercial_enforcement"] == "enforce"
        overview = client.get(
            "/billing", headers={"Authorization": f"Bearer {body['access_token']}"}
        ).json()
        assert overview["plan"]["code"] == "corretor_teste_15d"
        assert overview["status"] == "trial"
        assert overview["subscription"] is None
        assert overview["plans"][0]["code"] == "corretor_beta"
        expires = datetime.fromisoformat(overview["trial_ends_at"])
        assert timedelta(days=14, hours=23) < expires - datetime.now(UTC) <= timedelta(days=15)
        assert granted.json()["commercial_available"] == {
            "ai_attendance": 10,
            "property_search_standard": 20,
            "property_search_ai": 0,
            "image_optimization": 10,
        }
        assert (
            client.get(
                "/network/settings", headers={"Authorization": f"Bearer {body['access_token']}"}
            ).json()["eligible"]
            is True
        )
        repeat = client.post(
            "/platform/broker-test-access", headers=platform, json={"email": email}
        )
        assert repeat.status_code == 200
        assert (
            repeat.json()["commercial_cycle_ends_at"] == granted.json()["commercial_cycle_ends_at"]
        )

    slots = client.get("/platform/broker-test-access", headers=platform).json()
    assert slots == {"used": 3, "limit": 3}
    invitation = _create(client, platform)
    fourth = client.post(
        "/signup", json=_signup(invitation["code"], email="fourth@example.com")
    ).json()
    refused = client.post(
        "/platform/broker-test-access",
        headers=platform,
        json={"email": "fourth@example.com"},
    )
    assert refused.status_code == 409
    assert (
        client.get(
            "/billing", headers={"Authorization": f"Bearer {fourth['access_token']}"}
        ).json()["status"]
        == "pending"
    )

    email, body = accounts[0]
    tenant_id = UUID(body["tenant_id"])
    with client.app.state.container.database.session_factory() as session:
        commercial = CommercialEntitlementService(session)
        for resource, limit in (
            ("ai_attendance", 10),
            ("image_optimization", 10),
            ("property_search_standard", 20),
        ):
            for number in range(limit):
                key = f"test-{resource}-{number}"
                commercial.reserve(
                    tenant_id, resource=resource, idempotency_key=key, reference_id=None
                )
                commercial.settle(tenant_id, key)
            with pytest.raises(CommercialAllowanceExhausted):
                commercial.reserve(
                    tenant_id,
                    resource=resource,
                    idempotency_key=f"test-{resource}-over-limit",
                    reference_id=None,
                )
        past = datetime.now(UTC) - timedelta(seconds=1)
        session.execute(
            update(TenantCommercialSubscriptionModel)
            .where(TenantCommercialSubscriptionModel.tenant_id == tenant_id)
            .values(cycle_ends_at=past, trial_ends_at=past)
        )
        session.execute(
            update(CommercialEntitlementGrantModel)
            .where(CommercialEntitlementGrantModel.tenant_id == tenant_id)
            .values(expires_at=past)
        )
        session.commit()
        with pytest.raises(CommercialAllowanceExhausted):
            commercial.reserve(
                tenant_id,
                resource="property_search_standard",
                idempotency_key="expired-search",
                reference_id=None,
            )
    assert (
        client.get(
            "/network/settings", headers={"Authorization": f"Bearer {body['access_token']}"}
        ).json()["eligible"]
        is False
    )

    fake = FakeAsaasClient()
    monkeypatch.setattr(billing_api, "asaas_client_from_settings", lambda *_: fake)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    paid = client.post(
        "/billing/subscription",
        headers=headers,
        json={
            "plan_code": "corretor_beta",
            "billing_type": "PIX",
            "idempotency_key": "convert-after-test",
            "customer": {
                "name": "Broker Tester",
                "email": email,
                "cpf_cnpj": "12345678909",
            },
        },
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["subscription"]["value_cents"] == 5990
    assert (
        _confirm(
            client,
            "broker-test-paid",
            {
                "id": "pay_pack_1",
                "externalReference": fake.created_payments[0]["externalReference"],
            },
        )["outcome"]
        == "broker_invoice_paid"
    )
    after = client.get("/billing", headers=headers).json()
    assert after["status"] == "active"
    assert after["plan"]["code"] == "corretor_beta"
    assert after["trial_ends_at"] is None
