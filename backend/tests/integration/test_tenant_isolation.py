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
