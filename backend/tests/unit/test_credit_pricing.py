from decimal import Decimal

import pytest

from app.modules.billing_usage.service import chat_charge, image_token_charge


def test_chat_charge_uses_separate_input_cached_and_output_rates() -> None:
    charge = chat_charge(
        "gpt-5.4-mini",
        input_tokens=1_000,
        cached_input_tokens=200,
        output_tokens=500,
    )

    assert charge.provider_cost_usd == Decimal("0.002865")
    assert charge.retail_cost_usd == Decimal("0.0057300")
    assert charge.credits == 6


def test_image_charge_applies_configured_margin() -> None:
    charge = image_token_charge(
        "gpt-image-2",
        input_image_tokens=1_000,
        input_text_tokens=100,
        output_image_tokens=2_000,
    )

    assert charge.provider_cost_usd == Decimal("0.0685")
    assert charge.retail_cost_usd == Decimal("0.13700")
    assert charge.credits == 137


def test_unknown_model_must_not_be_billed_silently() -> None:
    with pytest.raises(ValueError, match="sem tarifa"):
        chat_charge("modelo-desconhecido", input_tokens=1, cached_input_tokens=0, output_tokens=1)
