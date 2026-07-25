import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from alembic import command
from app.config import Settings, get_settings

load_dotenv()

# Test-only defaults let unit tests import the ASGI module without developer secrets.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/imobos_unit")
os.environ.setdefault("JWT_SECRET", "test-only-secret-value-with-at-least-32-characters")

TEST_SECRET = "test-only-secret-value-with-at-least-32-characters"
TEST_WEBHOOK_SECRET = "test-only-webhook-secret"
TEST_PLATFORM_BOOTSTRAP_TOKEN = "test-only-platform-bootstrap-token-with-32-characters"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")
    return url


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> Generator[str, None, None]:
    previous_database_url = os.environ.get("DATABASE_URL")
    previous_jwt_secret = os.environ.get("JWT_SECRET")
    os.environ["DATABASE_URL"] = test_database_url
    os.environ["JWT_SECRET"] = TEST_SECRET
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    yield test_database_url
    command.downgrade(config, "base")
    if previous_database_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous_database_url
    if previous_jwt_secret is None:
        os.environ.pop("JWT_SECRET", None)
    else:
        os.environ["JWT_SECRET"] = previous_jwt_secret
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_database(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    if "integration" not in request.keywords:
        yield
        return
    url = request.getfixturevalue("migrated_database")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE ai_audit_logs, knowledge_chunks, knowledge_documents, "
                "property_demand_matches, properties, contacts, maintenance_tickets, lead_demands, "
                "message_jobs, messages, conversations, "
                "credit_ledger, credit_accounts, usage_records, platform_users, users, "
                "tenants CASCADE"
            )
        )
    yield
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE ai_audit_logs, knowledge_chunks, knowledge_documents, "
                "property_demand_matches, properties, contacts, maintenance_tickets, lead_demands, "
                "message_jobs, messages, conversations, "
                "credit_ledger, credit_accounts, usage_records, platform_users, users, "
                "tenants CASCADE"
            )
        )
    engine.dispose()


@pytest.fixture
def client(migrated_database: str, tmp_path: Path) -> Generator[TestClient, None, None]:
    from app.main import create_app

    settings = Settings(
        database_url=migrated_database,
        jwt_secret=TEST_SECRET,
        app_env="test",
        ai_auto_reply_enabled=False,
        ai_auto_send_to_channel=False,
        platform_bootstrap_token=TEST_PLATFORM_BOOTSTRAP_TOKEN,
        telegram_auto_reply_enabled=False,
        property_media_root=tmp_path / "property-images",
        openai_api_key=None,
        telegram_tenant_configs={
            "tenant-a": {
                "bot_token": "test-telegram-token-a",
                "webhook_secret": TEST_WEBHOOK_SECRET,
                "bot_username": "tenant_a_bot",
            },
            "tenant-b": {
                "bot_token": "test-telegram-token-b",
                "webhook_secret": TEST_WEBHOOK_SECRET,
                "bot_username": "tenant_b_bot",
            },
        },
        evolution_tenant_configs={
            "tenant-a": {
                "base_url": "https://evolution.invalid",
                "instance": "tenant-a",
                "api_key": "test-api-key-a",
                "webhook_secret": TEST_WEBHOOK_SECRET,
            },
            "tenant-b": {
                "base_url": "https://evolution.invalid",
                "instance": "tenant-b",
                "api_key": "test-api-key-b",
                "webhook_secret": TEST_WEBHOOK_SECRET,
            },
        },
        hubspot_tenant_configs={
            "tenant-a": {
                "base_url": "https://api.hubapi.invalid",
                "access_token": "test-hubspot-token-a",
                "pipeline_id": "pipeline-a",
                "stage_ids": {"qualified": "stage-qualified-a"},
                "owner_map": {"default": "owner-a", "handoff": "owner-handoff-a"},
            },
            "tenant-b": {
                "base_url": "https://api.hubapi.invalid",
                "access_token": "test-hubspot-token-b",
                "pipeline_id": "pipeline-b",
                "stage_ids": {"qualified": "stage-qualified-b"},
                "owner_map": {"default": "owner-b", "handoff": "owner-handoff-b"},
            },
        },
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
