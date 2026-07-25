import re

MIN_E164_DIGITS = 10
MAX_E164_DIGITS = 15
MAX_TELEGRAM_ID_DIGITS = 20


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
    return digits
