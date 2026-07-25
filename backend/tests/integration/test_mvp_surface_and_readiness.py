import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration


def test_readiness_checks_database_and_v2_routes_are_not_registered(
    client: TestClient,
) -> None:
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["database_revision"]

    paths = client.app.openapi()["paths"]
    assert "/integrations/evolution/whatsapp/connect" in paths
    assert "/integrations/telegram/connect" in paths
    assert not any(path.startswith("/capture") for path in paths)
    assert not any(path.startswith("/maintenance") for path in paths)
    assert not any("/tecimob" in path for path in paths)
    assert "/integrations/setup" not in paths
    assert "/properties/media-cleanup/process" not in paths


def test_readiness_is_generic_for_revision_mismatch_and_database_failure(
    client: TestClient, migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        connection.execute(text("UPDATE alembic_version SET version_num = 'mismatch'"))
    try:
        mismatch = client.get("/ready")
        assert mismatch.status_code == 503
        assert mismatch.json() == {"status": "not_ready"}
        assert "mismatch" not in mismatch.text
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": actual},
            )
        engine.dispose()

    def unavailable(*args, **kwargs):
        raise RuntimeError("postgresql://user:secret@private-host/database")

    with monkeypatch.context() as scoped:
        scoped.setattr(
            client.app.state.container.database, "session_factory", unavailable
        )
        failed = client.get("/ready")
    assert failed.status_code == 503
    assert failed.json() == {"status": "not_ready"}
    assert "secret" not in failed.text
    assert client.get("/ready").status_code == 200


def test_cors_preflight_is_allowlisted_and_wildcard_is_rejected(client: TestClient) -> None:
    settings = client.app.state.container.settings.model_copy(
        update={"cors_origins": ["https://tenant.example"]}
    )
    with TestClient(create_app(settings)) as cors_client:
        allowed = cors_client.options(
            "/contacts",
            headers={
                "Origin": "https://tenant.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = cors_client.options(
            "/contacts",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://tenant.example"
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers

    payload = client.app.state.container.settings.model_dump()
    payload["cors_origins"] = ["*"]
    with pytest.raises(ValueError, match="wildcard"):
        Settings.model_validate(payload)
