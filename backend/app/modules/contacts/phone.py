import re

MIN_E164_DIGITS = 10
MAX_E164_DIGITS = 15
MAX_TELEGRAM_ID_DIGITS = 20
BRAZIL_COUNTRY_CODE = "55"
# Area code plus number, without the country code: 10 digits (landline) or 11 (mobile).
BRAZIL_NATIONAL_LENGTHS = (10, 11)


def normalize_contact_phone(value: str) -> str:
    raw = value.strip()
    if raw.lower().startswith("telegram:"):
        identifier = raw.split(":", 1)[1].strip()
        if not identifier.isdigit() or len(identifier) > MAX_TELEGRAM_ID_DIGITS:
            raise ValueError("Invalid Telegram contact identifier")
        return f"telegram:{identifier}"
    digits = re.sub(r"\D", "", raw)
    if not MIN_E164_DIGITS <= len(digits) <= MAX_E164_DIGITS:
        raise ValueError("Phone number must contain between 10 and 15 digits")
    # WhatsApp always reports numbers with the country code; typed ones often lack it.
    # Completing them keeps one contact per person instead of "51..." and "5551...".
    if len(digits) in BRAZIL_NATIONAL_LENGTHS:
        return BRAZIL_COUNTRY_CODE + digits
    return digits


def phone_identity_key(value: str) -> str:
    """Same key for every way one Brazilian number is written.

    Ignores the country code and the mobile ninth digit, which WhatsApp sometimes omits:
    "5551991129452", "555191129452" and "51991129452" all give "5191129452".
    """

    raw = value.strip()
    if raw.lower().startswith("telegram:"):
        return raw.lower()
    digits = re.sub(r"\D", "", raw)
    if len(digits) in (12, 13) and digits.startswith(BRAZIL_COUNTRY_CODE):
        digits = digits[2:]
    if len(digits) == 11 and digits[2] == "9":
        digits = digits[:2] + digits[3:]
    return digits


def phone_variants(normalized: str) -> list[str]:
    """Stored forms that belong to the same person as an already normalized number."""

    variants = [normalized]
    if normalized.startswith(BRAZIL_COUNTRY_CODE):
        domestic = normalized[2:]
        if len(domestic) == 11 and domestic[2] == "9":
            variants.append(BRAZIL_COUNTRY_CODE + domestic[:2] + domestic[3:])
        elif len(domestic) == 10 and domestic[2] in "6789":
            variants.append(BRAZIL_COUNTRY_CODE + domestic[:2] + "9" + domestic[2:])
    return variants
