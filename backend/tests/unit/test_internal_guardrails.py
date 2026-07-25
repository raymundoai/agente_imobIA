from app.modules.maintenance.application.use_cases import detect_restricted_intent


def test_internal_guardrails_detect_financial_and_legal_handoff_cases() -> None:
    assert (
        detect_restricted_intent("Quero negociar valor e pedir desconto") == "financial_negotiation"
    )
    assert detect_restricted_intent("Preciso cancelar contrato por rescisão") == "legal_or_contract"
    assert detect_restricted_intent("Como pego segunda via do boleto?") is None
