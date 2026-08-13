import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

PASSWORD = "valid-test-password-123"


def _provision(client: TestClient, slug: str = "secure-team") -> tuple[dict, dict]:
    tenant = client.post(
        "/tenants",
        json={
            "name": "Secure Team",
            "slug": slug,
            "admin_name": "Admin Principal",
            "admin_email": "admin@example.com",
            "admin_password": PASSWORD,
        },
    )
    assert tenant.status_code == 201, tenant.text
    login = client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": "admin@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    return tenant.json(), login.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_invitation_is_single_use_and_activates_user(client: TestClient) -> None:
    _, admin_tokens = _provision(client)
    admin_headers = _headers(admin_tokens["access_token"])

    invited = client.post(
        "/users/invitations",
        headers=admin_headers,
        json={"name": "Maria Corretora", "email": "maria@example.com", "role": "corretor"},
    )
    assert invited.status_code == 201, invited.text
    payload = invited.json()
    assert payload["user"]["status"] == "invited"
    assert payload["user"]["must_change_password"] is True
    assert len(payload["token"]) >= 32

    accepted = client.post(
        "/auth/accept-invitation",
        json={"token": payload["token"], "password": "new-secure-password-123"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["tenant_slug"] == "secure-team"
    me = client.get("/users/me", headers=_headers(accepted.json()["access_token"]))
    assert me.status_code == 200, me.text
    assert me.json()["status"] == "active"
    assert me.json()["must_change_password"] is False

    reused = client.post(
        "/auth/accept-invitation",
        json={"token": payload["token"], "password": "another-secure-password-123"},
    )
    assert reused.status_code == 401
    audit = client.get("/users/audit", headers=admin_headers).json()
    assert {item["action"] for item in audit} >= {"user_invited", "password_defined"}


def test_role_change_invalidates_access_and_refresh_tokens_immediately(
    client: TestClient,
) -> None:
    _, admin_tokens = _provision(client, "session-role")
    admin_headers = _headers(admin_tokens["access_token"])
    created = client.post(
        "/users",
        headers=admin_headers,
        json={
            "name": "Gestora",
            "email": "gestora@example.com",
            "password": PASSWORD,
            "role": "gestor",
        },
    )
    assert created.status_code == 201, created.text
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "session-role",
            "email": "gestora@example.com",
            "password": PASSWORD,
        },
    ).json()
    assert client.get("/users", headers=_headers(login["access_token"])).status_code == 200

    changed = client.patch(
        f"/users/{created.json()['id']}",
        headers=admin_headers,
        json={"role": "corretor"},
    )
    assert changed.status_code == 200, changed.text
    assert client.get("/users/me", headers=_headers(login["access_token"])).status_code == 401
    refresh = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refresh.status_code == 401


def test_admin_cannot_change_own_role_or_status_even_with_another_admin(
    client: TestClient,
) -> None:
    _, tokens = _provision(client, "self-guard")
    headers = _headers(tokens["access_token"])
    current = client.get("/users/me", headers=headers).json()
    assert current["is_master"] is True
    second = client.post(
        "/users",
        headers=headers,
        json={
            "name": "Segundo Admin",
            "email": "second-admin@example.com",
            "password": PASSWORD,
            "role": "admin",
        },
    )
    assert second.status_code == 201, second.text

    demote = client.patch(f"/users/{current['id']}", headers=headers, json={"role": "gestor"})
    deactivate = client.patch(
        f"/users/{current['id']}", headers=headers, json={"status": "inactive"}
    )
    assert demote.status_code == 409
    assert deactivate.status_code == 409
    assert "administrador principal" in demote.json()["detail"]


def test_only_master_can_delete_other_profiles(client: TestClient) -> None:
    _, master_tokens = _provision(client, "master-delete")
    master_headers = _headers(master_tokens["access_token"])
    master = client.get("/users/me", headers=master_headers).json()
    second_admin = client.post(
        "/users",
        headers=master_headers,
        json={
            "name": "Admin Secundário",
            "email": "secondary@example.com",
            "password": PASSWORD,
            "role": "admin",
        },
    )
    assert second_admin.status_code == 201, second_admin.text
    assert second_admin.json()["is_master"] is False
    secondary_tokens = client.post(
        "/auth/login",
        json={
            "tenant_slug": "master-delete",
            "email": "secondary@example.com",
            "password": PASSWORD,
        },
    ).json()
    secondary_headers = _headers(secondary_tokens["access_token"])
    target = client.post(
        "/users",
        headers=master_headers,
        json={
            "name": "Perfil Removível",
            "email": "remove@example.com",
            "password": PASSWORD,
            "role": "corretor",
        },
    ).json()

    denied = client.delete(f"/users/{target['id']}", headers=secondary_headers)
    assert denied.status_code == 403
    self_delete = client.delete(f"/users/{master['id']}", headers=master_headers)
    assert self_delete.status_code == 409

    deleted = client.delete(f"/users/{target['id']}", headers=master_headers)
    assert deleted.status_code == 204, deleted.text
    assert target["id"] not in {
        user["id"] for user in client.get("/users", headers=master_headers).json()
    }
    audit = client.get("/users/audit", headers=master_headers).json()
    deletion = next(item for item in audit if item["action"] == "user_deleted")
    assert deletion["target_user_id"] is None
    assert deletion["changes"]["name"] == "Perfil Removível"


def test_revoke_sessions_and_team_visibility_are_enforced(client: TestClient) -> None:
    _, admin_tokens = _provision(client, "revoke-team")
    admin_headers = _headers(admin_tokens["access_token"])
    created = client.post(
        "/users",
        headers=admin_headers,
        json={
            "name": "Corretora",
            "email": "corretora@example.com",
            "password": PASSWORD,
            "role": "corretor",
        },
    ).json()
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "revoke-team",
            "email": "corretora@example.com",
            "password": PASSWORD,
        },
    ).json()
    user_headers = _headers(login["access_token"])
    assert client.get("/users/me", headers=user_headers).status_code == 200
    assert client.get("/users", headers=user_headers).status_code == 403

    revoked = client.post(f"/users/{created['id']}/revoke-sessions", headers=admin_headers)
    assert revoked.status_code == 200, revoked.text
    assert client.get("/users/me", headers=user_headers).status_code == 401
    assert (
        client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code
        == 401
    )


def test_password_setup_revokes_old_session_and_accepts_new_password(
    client: TestClient,
) -> None:
    _, admin_tokens = _provision(client, "password-reset")
    admin_headers = _headers(admin_tokens["access_token"])
    created = client.post(
        "/users",
        headers=admin_headers,
        json={
            "name": "Atendente",
            "email": "atendente@example.com",
            "password": PASSWORD,
            "role": "atendente",
        },
    ).json()
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "password-reset",
            "email": "atendente@example.com",
            "password": PASSWORD,
        },
    ).json()

    setup = client.post(f"/users/{created['id']}/password-setup", headers=admin_headers)
    assert setup.status_code == 200, setup.text
    assert client.get("/users/me", headers=_headers(login["access_token"])).status_code == 401
    old_password_login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "password-reset",
            "email": "atendente@example.com",
            "password": PASSWORD,
        },
    )
    assert old_password_login.status_code == 401
    accepted = client.post(
        "/auth/accept-invitation",
        json={"token": setup.json()["token"], "password": "replacement-password-123"},
    )
    assert accepted.status_code == 200, accepted.text


def test_attendant_has_read_only_access_to_property_demands(client: TestClient) -> None:
    _, admin_tokens = _provision(client, "attendant-demands")
    admin_headers = _headers(admin_tokens["access_token"])
    created = client.post(
        "/users",
        headers=admin_headers,
        json={
            "name": "Atendente",
            "email": "readonly@example.com",
            "password": PASSWORD,
            "role": "atendente",
        },
    )
    assert created.status_code == 201, created.text
    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": "attendant-demands",
            "email": "readonly@example.com",
            "password": PASSWORD,
        },
    )
    attendant_headers = _headers(login.json()["access_token"])

    assert client.get("/leads/demands", headers=attendant_headers).status_code == 200
    denied = client.post(
        "/leads/demands",
        headers=attendant_headers,
        json={
            "lead_name": "Sem permissão",
            "phone": "5551999881100",
            "purpose": "rent",
            "city": "Porto Alegre",
            "state": "RS",
        },
    )
    assert denied.status_code == 403
