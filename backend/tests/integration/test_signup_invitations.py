"""Closed beta invitation lifecycle and automatic commercial eligibility."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.modules.billing_usage.commercial import CommercialEntitlementService
from app.modules.platform.invitations import SignupInvitationModel
from tests.integration.test_platform_admin import _bootstrap

pytestmark = pytest.mark.integration


def _auth(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_bootstrap(client)}"}


def _signup(code: str | None = None, **overrides: object) -> dict[str, object]:
    return {
        "company_name": "Ana Corretora",
        "admin_name": "Ana Corretora",
        "email": "ana@example.com",
        "password": "long-test-password-123",
        "business_type": "broker",
        "accept_terms": True,
        **({"invitation_code": code} if code is not None else {}),
        **overrides,
    }


def _create(client: TestClient, auth: dict[str, str]) -> dict:
    response = client.post("/platform/signup-invitations", headers=auth, json={})
    assert response.status_code == 201, response.text
    invitation = response.json()
    validity = datetime.fromisoformat(invitation["expires_at"]) - datetime.fromisoformat(
        invitation["created_at"]
    )
    assert validity == timedelta(days=90)
    return invitation


def test_invited_broker_gets_beta_offer_and_code_cannot_be_reused(client: TestClient) -> None:
    client.app.state.container.settings.public_signup_enabled = True
    auth = _auth(client)
    assert client.post("/platform/signup-invitations", json={}).status_code == 401
    invitation = _create(client, auth)
    listed = client.get("/platform/signup-invitations", headers=auth).json()
    assert len(listed) == 1
    assert "code" not in listed[0] and "code_hash" not in listed[0]
    assert listed[0]["code_suffix"] == invitation["code"].replace("-", "")[-4:]

    assert client.post("/signup", json=_signup()).status_code == 403
    invalid = client.post("/signup", json=_signup("IMB-000000-000000-000000-000000"))
    assert invalid.status_code == 403
    agency = client.post("/signup", json=_signup(invitation["code"], business_type="agency"))
    assert agency.status_code == 403

    created = client.post("/signup", json=_signup(invitation["code"].lower()))
    assert created.status_code == 201, created.text
    headers = {"Authorization": f"Bearer {created.json()['access_token']}"}
    billing = client.get("/billing", headers=headers).json()
    assert billing["beta_pricing"] is True
    assert [plan["code"] for plan in billing["plans"]] == ["corretor_beta"]
    assert billing["plans"][0]["monthly_price_cents"] == 5990

    reused = client.post("/signup", json=_signup(invitation["code"], email="other@example.com"))
    assert reused.status_code == 403
    listed = client.get("/platform/signup-invitations", headers=auth).json()
    assert listed[0]["redeemed_at"] is not None


def test_revoked_and_expired_invitations_cannot_open_accounts(client: TestClient) -> None:
    client.app.state.container.settings.public_signup_enabled = True
    auth = _auth(client)
    revoked = _create(client, auth)
    response = client.post(f"/platform/signup-invitations/{revoked['id']}/revoke", headers=auth)
    assert response.status_code == 200
    assert client.post("/signup", json=_signup(revoked["code"])).status_code == 403

    expired = _create(client, auth)
    with client.app.state.container.database.session_factory() as session:
        model = session.get(SignupInvitationModel, UUID(expired["id"]))
        assert model is not None
        model.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert client.post("/signup", json=_signup(expired["code"])).status_code == 403


def test_failed_signup_keeps_invitation_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.app.state.container.settings.public_signup_enabled = True
    auth = _auth(client)
    invitation = _create(client, auth)
    original = CommercialEntitlementService.start_pending

    def fail_once(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated database provisioning failure")

    monkeypatch.setattr(CommercialEntitlementService, "start_pending", fail_once)
    with pytest.raises(RuntimeError, match="simulated database provisioning failure"):
        client.post("/signup", json=_signup(invitation["code"]))
    monkeypatch.setattr(CommercialEntitlementService, "start_pending", original)

    listed = client.get("/platform/signup-invitations", headers=auth).json()
    assert listed[0]["redeemed_at"] is None
    assert client.get("/platform/tenants", headers=auth).json() == []
    assert client.post("/signup", json=_signup(invitation["code"])).status_code == 201
