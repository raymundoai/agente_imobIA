from app.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:password@localhost/database",
        jwt_secret="a-secure-test-secret-with-at-least-32-characters",
        **overrides,
    )


def test_empty_optional_storage_environment_values_become_none() -> None:
    settings = _settings(
        property_media_legacy_root="",
        property_s3_endpoint_url=" ",
        property_s3_region="",
        property_s3_access_key="",
        property_s3_secret_key=" ",
    )

    assert settings.property_media_legacy_root is None
    assert settings.property_s3_endpoint_url is None
    assert settings.property_s3_region is None
    assert settings.property_s3_access_key is None
    assert settings.property_s3_secret_key is None


def test_s3_accepts_default_credential_chain_without_explicit_keys() -> None:
    settings = _settings(
        property_storage_backend="s3",
        property_s3_bucket="private-property-media",
        property_s3_access_key="",
        property_s3_secret_key="",
    )

    assert settings.property_storage_backend == "s3"
    assert settings.property_s3_bucket == "private-property-media"
    assert settings.property_s3_access_key is None
    assert settings.property_s3_secret_key is None
