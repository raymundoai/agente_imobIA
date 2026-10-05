import pytest


def test_empty_optional_keys_in_env_mean_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    for name in ("OPENAI_API_KEY", "INTEGRATION_SECRET_KEY", "PLATFORM_BOOTSTRAP_TOKEN"):
        monkeypatch.setenv(name, "")
    settings = Settings(
        database_url="postgresql://user:pass@localhost/db",
        jwt_secret="x" * 40,
        _env_file=None,
    )
    assert settings.openai_api_key is None
    assert settings.integration_secret_key is None
    assert settings.platform_bootstrap_token is None
