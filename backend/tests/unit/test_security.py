import ast
from pathlib import Path
from uuid import uuid4

import pytest

from app.shared.errors.exceptions import AuthenticationError
from app.shared.security.jwt import JwtTokenService
from app.shared.security.passwords import Argon2PasswordHasher


def test_domain_layers_do_not_import_adapters() -> None:
    modules_root = Path(__file__).parents[2] / "app" / "modules"
    violations: list[str] = []
    for path in modules_root.glob("*/domain/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            if any(".adapters" in name for name in imported):
                violations.append(str(path.relative_to(modules_root)))

    assert violations == []


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("a-long-test-password")

    assert hashed != "a-long-test-password"
    assert hasher.verify("a-long-test-password", hashed)
    assert not hasher.verify("incorrect-password", hashed)


def test_access_token_cannot_be_used_as_refresh_token() -> None:
    service = JwtTokenService(
        secret="test-only-secret-value-with-at-least-32-characters",
        algorithm="HS256",
        access_ttl_minutes=15,
        refresh_ttl_days=7,
    )
    token = service.create_access_token(uuid4(), uuid4(), "admin")

    with pytest.raises(AuthenticationError):
        service.decode(token, expected_type="refresh")
