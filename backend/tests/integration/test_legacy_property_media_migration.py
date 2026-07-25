import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from alembic import command
from app.modules.properties.migrate_legacy_media import migrate

pytestmark = pytest.mark.integration


def test_backfill_and_file_migration_preserve_legacy_image(
    client: TestClient, migrated_database: str, tmp_path: Path
) -> None:
    password = "valid-test-password-123"
    suffix = uuid4().hex[:8]
    slug = f"tenant-media-{suffix}"
    email = f"media-{suffix}@example.com"
    tenant = client.post(
        "/tenants",
        json={
            "name": "Tenant mídia",
            "slug": slug,
            "admin_name": "Admin",
            "admin_email": email,
            "admin_password": password,
        },
    ).json()
    token = client.post(
        "/auth/login",
        json={
            "tenant_slug": slug,
            "email": email,
            "password": password,
        },
    ).json()["access_token"]
    created = client.post(
        "/properties",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Imóvel legado",
            "purpose": "buy",
            "property_type": "casa",
            "category": "residential",
            "sale_price": 500000,
            "address": {
                "street": "Rua Teste",
                "neighborhood": "Centro",
                "city": "São Paulo",
                "state": "SP",
            },
        },
    ).json()

    config = Config("alembic.ini")
    command.downgrade(config, "20260725_0014")
    legacy_url = f"/media/properties/{tenant['id']}/legacy.png"
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE properties SET images = CAST(:images AS jsonb) WHERE id = :id"),
            {
                "id": created["id"],
                "images": json.dumps(
                    [
                        {
                            "url": legacy_url,
                            "original_name": "fachada.png",
                            "content_type": "image/png",
                            "size": 16,
                        }
                    ]
                ),
            },
        )
    command.upgrade(config, "head")

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT original_storage_key, legacy_url, is_primary, sort_order "
                "FROM property_images WHERE property_id = :id"
            ),
            {"id": created["id"]},
        ).one()
    assert row == (f"{tenant['id']}/legacy.png", legacy_url, True, 0)

    legacy_root = tmp_path / "legacy"
    source = legacy_root / tenant["id"] / "legacy.png"
    source.parent.mkdir(parents=True)
    content = b"\x89PNG\r\n\x1a\nlegacy"
    source.write_bytes(content)
    client.app.state.container.settings.property_media_legacy_root = legacy_root
    first = migrate(client.app.state.container)
    second = migrate(client.app.state.container)
    assert first["migrated"] == 1
    assert second["skipped"] == 1
    with client.app.state.container.property_image_storage.open(
        tenant["id"], f"{tenant['id']}/legacy.png"
    ) as stored:
        assert stored.read() == content
    engine.dispose()
