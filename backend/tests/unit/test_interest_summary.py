from app.modules.leads.application.use_cases import describe_interest


def test_interest_reads_as_a_sentence_in_portuguese() -> None:
    assert (
        describe_interest("rent", "comercial", "São Paulo", ["Centro"])
        == "Aluguel de comercial em São Paulo (Centro)"
    )
    assert (
        describe_interest("buy", "apartamento", "Porto Alegre", ["Moinhos", "Bela Vista"])
        == "Compra de apartamento em Porto Alegre (Moinhos, Bela Vista)"
    )
    assert describe_interest("buy", None, "Canoas") == "Compra de imóvel em Canoas"
    assert describe_interest(None, "sala_comercial", None) == "Sala comercial"
    assert describe_interest(None, None, None) == "Interesse imobiliário"
