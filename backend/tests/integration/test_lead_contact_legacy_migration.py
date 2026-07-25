import os
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from alembic import command

pytestmark = pytest.mark.integration


def test_migration_merges_legacy_contacts_without_losing_curated_data(
    client: TestClient, migrated_database: str
) -> None:
    created = client.post(
        "/tenants",
        json={
            "name": "Legado",
            "slug": "legado",
            "admin_name": "Admin",
            "admin_email": "admin@legado.example.com",
            "admin_password": "valid-test-password-123",
        },
    )
    assert created.status_code == 201, created.text
    tenant_id = created.json()["id"]
    os.environ["DATABASE_URL"] = migrated_database
    config = Config("alembic.ini")
    command.downgrade(config, "20260725_0011")

    engine = create_engine(migrated_database)
    curated_id, duplicate_id, conversation_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO contacts "
                "(id, tenant_id, name, phone, email, kind, status, tags, interest, notes) VALUES "
                "(:curated, :tenant, 'Nome Curado', '+55 (11) 99999-0000', "
                "'curado@test.dev', 'owner', 'inactive', ARRAY['vip'], NULL, NULL), "
                "(:duplicate, :tenant, 'Nome Automático', '5511999990000', "
                "NULL, 'lead', 'active', ARRAY['whatsapp'], 'Apartamento', 'Nota complementar')"
            ),
            {
                "curated": curated_id,
                "duplicate": duplicate_id,
                "tenant": tenant_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO contacts "
                "(id, tenant_id, name, phone, kind, status, tags) VALUES "
                "(:id, :tenant, 'Inválido', 'telegram:', 'lead', 'active', ARRAY[]::text[])"
            ),
            {"id": uuid4(), "tenant": tenant_id},
        )
        connection.execute(
            text(
                "INSERT INTO conversations "
                "(id, tenant_id, channel, phone, status, mode) VALUES "
                "(:id, :tenant, 'whatsapp', '55 11 99999-0000', 'open', 'ai')"
            ),
            {"id": conversation_id, "tenant": tenant_id},
        )
        for name, phone in (
            ("Demanda antiga", "+55 11 99999-0000"),
            ("Demanda recente", "5511999990000"),
        ):
            connection.execute(
                text(
                    "INSERT INTO lead_demands "
                    "(id, tenant_id, lead_name, phone, status, notes) "
                    "VALUES (:id, :tenant, :name, :phone, 'qualified', :name)"
                ),
                {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "name": name,
                    "phone": phone,
                },
            )
    command.upgrade(config, "head")

    with engine.connect() as connection:
        contacts = (
            connection.execute(
                text(
                    "SELECT name, phone, email, kind, status, tags, interest, notes "
                    "FROM contacts WHERE tenant_id = :tenant ORDER BY phone"
                ),
                {"tenant": tenant_id},
            )
            .mappings()
            .all()
        )
        demands = (
            connection.execute(
                text(
                    "SELECT status, contact_id, conversation_id FROM lead_demands "
                    "WHERE tenant_id = :tenant ORDER BY created_at"
                ),
                {"tenant": tenant_id},
            )
            .mappings()
            .all()
        )
    engine.dispose()

    merged = next(item for item in contacts if item["phone"] == "5511999990000")
    assert merged["name"] == "Nome Curado"
    assert merged["email"] == "curado@test.dev"
    assert merged["kind"] == "owner"
    assert merged["status"] == "inactive"
    assert set(merged["tags"]) >= {"vip", "whatsapp", "qualification"}
    assert merged["interest"] == "Apartamento"
    assert merged["notes"] == "Nota complementar"
    assert any(item["phone"] == "telegram:" for item in contacts)
    assert len(demands) == 2
    assert sum(item["status"] != "closed" for item in demands) == 1
    assert all(item["contact_id"] is not None for item in demands)
    assert all(item["conversation_id"] is None for item in demands)
