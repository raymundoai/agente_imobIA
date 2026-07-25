def detect_restricted_intent(text: str) -> str | None:
    normalized = text.lower()
    groups = {
        "financial_negotiation": [
            "desconto",
            "parcelamento",
            "negociar valor",
            "abaixar aluguel",
            "inadimplência",
            "inadimplencia",
        ],
        "legal_or_contract": [
            "jurídico",
            "juridico",
            "processar",
            "rescisão",
            "rescisao",
            "cancelar contrato",
            "alterar contrato",
            "quebrar contrato",
        ],
    }
    for reason, terms in groups.items():
        if any(term in normalized for term in terms):
            return reason
    return None
