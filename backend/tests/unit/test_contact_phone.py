import pytest

from app.modules.contacts.phone import normalize_contact_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+55 (11) 99999-0000", "5511999990000"),
        ("55 11 99999-0000", "5511999990000"),
        ("telegram:321", "telegram:321"),
        (" Telegram: 321 ", "telegram:321"),
    ],
)
def test_normalize_contact_phone_uses_stable_channel_identity(raw: str, expected: str) -> None:
    assert normalize_contact_phone(raw) == expected


def test_normalize_contact_phone_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        normalize_contact_phone("()-")
