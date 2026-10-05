import pytest

from app.modules.contacts.phone import normalize_contact_phone, phone_identity_key, phone_variants


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("51991129452", "5551991129452"),
        ("(51) 3333-4444", "555133334444"),
        ("+55 51 99112-9452", "5551991129452"),
        ("555191129452", "555191129452"),
        ("telegram:123", "telegram:123"),
    ],
)
def test_brazilian_numbers_are_stored_with_the_country_code(typed: str, stored: str) -> None:
    assert normalize_contact_phone(typed) == stored


def test_every_way_of_writing_a_mobile_is_the_same_person() -> None:
    keys = {
        phone_identity_key(normalize_contact_phone(value))
        for value in ("51991129452", "5551991129452", "555191129452")
    }
    assert keys == {"5191129452"}
    assert set(phone_variants("5551991129452")) == {"5551991129452", "555191129452"}
    assert set(phone_variants("555191129452")) == {"555191129452", "5551991129452"}


def test_landlines_do_not_gain_a_ninth_digit() -> None:
    assert phone_variants("555133334444") == ["555133334444"]

