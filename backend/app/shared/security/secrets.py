import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretCipher:
    def __init__(self, application_secret: str) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(application_secret.encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str | None:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            return None


def integration_cipher(application_secret: str, dedicated_secret: str | None) -> SecretCipher:
    return SecretCipher(dedicated_secret or application_secret)
