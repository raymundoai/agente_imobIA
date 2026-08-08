from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.modules.users.adapters.repositories import SqlAlchemyUserRepository
from app.modules.users.domain.entities import User, UserRole
from app.shared.security.passwords import Argon2PasswordHasher

pytestmark = pytest.mark.integration


def _provision(client: TestClient, slug: str, email: str) -> tuple[dict, str]:
    password = "valid-test-password-123"
    response = client.post(
        "/tenants",
        json={
            "name": f"Tenant {slug}",
            "slug": slug,
            "admin_name": "Admin",
            "admin_email": email,
            "admin_password": password,
        },
    )
    assert response.status_code == 201, response.text
    login = client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return response.json(), login.json()["access_token"]


def test_user_repository_requires_matching_tenant_scope(migrated_database: str) -> None:
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()
    # Tenants are provisioned through the API in the next test; this test focuses on
    # the repository guard and creates valid parent rows through SQLAlchemy models.
    from app.modules.tenants.adapters.models import TenantModel

    engine = create_engine(migrated_database)
    hasher = Argon2PasswordHasher()
    with Session(engine) as session:
        session.add_all(
            [
                TenantModel(
                    id=tenant_a_id, name="A", slug="tenant-a", status="active", settings={}
                ),
                TenantModel(
                    id=tenant_b_id, name="B", slug="tenant-b", status="active", settings={}
                ),
            ]
        )
        session.commit()
        repository = SqlAlchemyUserRepository(session)
        user = User(
            tenant_id=tenant_a_id,
            name="Scoped User",
            email="scoped@example.test",
            hashed_password=hasher.hash("valid-test-password-123"),
            role=UserRole.CORRETOR,
        )
        repository.add(tenant_a_id, user)

        assert repository.get_by_id(tenant_a_id, user.id) is not None
        assert repository.get_by_id(tenant_b_id, user.id) is None
        assert repository.get_by_email(tenant_b_id, user.email) is None
        assert repository.list(tenant_b_id) == []
    engine.dispose()


def test_api_never_exposes_users_or_tenant_across_tenants(client: TestClient) -> None:
    # The same email may belong to two tenants; tenant_slug must select the scope.
    tenant_a, token_a = _provision(client, "tenant-a", "admin@example.com")
    tenant_b, token_b = _provision(client, "tenant-b", "admin@example.com")

    created = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Agent A",
            "email": "agent-a@example.com",
            "password": "valid-test-password-123",
            "role": "corretor",
        },
    )
    assert created.status_code == 201, created.text
    user_a_id = created.json()["id"]

    users_b = client.get("/users", headers={"Authorization": f"Bearer {token_b}"})
    assert users_b.status_code == 200
    assert all(user["id"] != user_a_id for user in users_b.json())

    update_as_b = client.patch(
        f"/users/{user_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"status": "inactive"},
    )
    assert update_as_b.status_code == 404

    tenant_as_b = client.get(
        f"/tenants/{tenant_a['id']}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert tenant_as_b.status_code == 404
    assert tenant_a["id"] != tenant_b["id"]


def test_agent_settings_update_preserves_integrations_and_can_disable_agent(
    client: TestClient,
) -> None:
    tenant, token = _provision(client, "agent-settings", "admin@agent-settings.example.com")
    headers = {"Authorization": f"Bearer {token}"}
    initial = client.patch(
        f"/tenants/{tenant['id']}/settings",
        headers=headers,
        json={
            "settings": {
                "profile": {"display_name": "Imobiliária Teste"},
                "agents": {"leads": {"status": "active"}},
            }
        },
    )
    assert initial.status_code == 200, initial.text

    updated = client.patch(
        f"/tenants/{tenant['id']}/settings/agents",
        headers=headers,
        json={
            "agents": {
                "leads": {
                    "name": "Agente de Leads",
                    "status": "inactive",
                    "goal": "Atender leads",
                }
            }
        },
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["settings"]["agents"]["leads"]["status"] == "inactive"
    assert updated.json()["settings"]["profile"]["display_name"] == "Imobiliária Teste"


def test_profile_settings_update_preserves_agents_and_integrations(client: TestClient) -> None:
    tenant, token = _provision(client, "profile-settings", "admin@profile-settings.example.com")
    headers = {"Authorization": f"Bearer {token}"}
    initial = client.patch(
        f"/tenants/{tenant['id']}/settings",
        headers=headers,
        json={
            "settings": {
                "agents": {"leads": {"status": "active"}},
                "integrations": {"evolution": {"status": "connected"}},
            }
        },
    )
    assert initial.status_code == 200, initial.text

    updated = client.patch(
        f"/tenants/{tenant['id']}/settings/profile",
        headers=headers,
        json={
            "profile": {
                "display_name": "Imobiliária Teste",
                "business_hours": {
                    "timezone": "America/Sao_Paulo",
                    "days": {"monday": {"enabled": True, "start": "08:30", "end": "18:00"}},
                },
            }
        },
    )

    assert updated.status_code == 200, updated.text
    settings = updated.json()["settings"]
    assert settings["profile"]["business_hours"]["days"]["monday"]["start"] == "08:30"
    assert settings["agents"]["leads"]["status"] == "active"
    assert settings["integrations"]["evolution"]["status"] == "connected"


def test_profile_settings_reject_invalid_document_and_business_hours(
    client: TestClient,
) -> None:
    tenant, token = _provision(
        client, "profile-validation", "admin@profile-validation.example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}

    invalid_document = client.patch(
        f"/tenants/{tenant['id']}/settings/profile",
        headers=headers,
        json={"profile": {"document_type": "cpf", "document_number": "11111111111"}},
    )
    invalid_hours = client.patch(
        f"/tenants/{tenant['id']}/settings/profile",
        headers=headers,
        json={
            "profile": {
                "business_hours": {
                    "timezone": "America/Sao_Paulo",
                    "days": {
                        "monday": {"enabled": True, "start": "18:00", "end": "09:00"}
                    },
                }
            }
        },
    )

    assert invalid_document.status_code == 422, invalid_document.text
    assert invalid_hours.status_code == 422, invalid_hours.text


def test_channel_settings_use_dedicated_endpoint_and_preserve_integrations(
    client: TestClient,
) -> None:
    tenant, token = _provision(client, "channel-settings", "admin@channels.example.com")
    headers = {"Authorization": f"Bearer {token}"}
    initial = client.patch(
        f"/tenants/{tenant['id']}/settings",
        headers=headers,
        json={"settings": {"integrations": {"evolution": {"status": "connected"}}}},
    )
    assert initial.status_code == 200, initial.text

    updated = client.patch(
        f"/tenants/{tenant['id']}/settings/channels",
        headers=headers,
        json={
            "channels": {
                "whatsapp": {"status": "connected", "agents": []},
                "telegram": {"status": "pending", "agents": ["leads"]},
            }
        },
    )

    assert updated.status_code == 200, updated.text
    settings = updated.json()["settings"]
    assert settings["channels"]["whatsapp"]["agents"] == []
    assert settings["integrations"]["evolution"]["status"] == "connected"


def test_last_active_admin_cannot_be_demoted_or_deactivated(client: TestClient) -> None:
    _, token = _provision(client, "admin-guard", "admin@guard.example.com")
    headers = {"Authorization": f"Bearer {token}"}
    users = client.get("/users", headers=headers).json()
    admin_id = users[0]["id"]

    demote = client.patch(
        f"/users/{admin_id}", headers=headers, json={"role": "gestor"}
    )
    deactivate = client.patch(
        f"/users/{admin_id}", headers=headers, json={"status": "inactive"}
    )

    assert demote.status_code == 409, demote.text
    assert deactivate.status_code == 409, deactivate.text
    assert "administrador ativo" in demote.json()["detail"]
