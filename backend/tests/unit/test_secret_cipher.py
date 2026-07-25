from app.shared.security.secrets import SecretCipher


def test_integration_secret_can_be_decrypted_during_key_rotation() -> None:
    old = SecretCipher("old-dedicated-secret")
    current = SecretCipher("new-dedicated-secret")
    encrypted = old.encrypt("webhook-value")

    assert current.decrypt(encrypted) is None
    assert old.decrypt(encrypted) == "webhook-value"
    migrated = current.encrypt(old.decrypt(encrypted) or "")
    assert current.decrypt(migrated) == "webhook-value"
