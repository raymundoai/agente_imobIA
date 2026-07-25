from pwdlib import PasswordHash

from app.modules.auth.ports.security import PasswordHasherPort


class Argon2PasswordHasher(PasswordHasherPort):
    def __init__(self) -> None:
        self._password_hash = PasswordHash.recommended()

    def hash(self, plain_password: str) -> str:
        return self._password_hash.hash(plain_password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return self._password_hash.verify(plain_password, hashed_password)
