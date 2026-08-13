from app.modules.capture.federated import _snapshot_meets_required_constraints


def test_snapshot_constraints_hide_incompatible_legacy_results() -> None:
    filters = {
        "purpose": "buy",
        "city": "Porto Alegre",
        "state": "RS",
        "price_min": "400000",
        "price_max": "1000000",
    }
    compatible = {
        "purpose": "both",
        "city": "Porto Alegre",
        "state": "RS",
        "price": "900000",
        "sale_price": "900000",
        "rent_price": "4500",
    }

    assert _snapshot_meets_required_constraints(compatible, filters)
    assert not _snapshot_meets_required_constraints(
        {**compatible, "city": "Novo Hamburgo"}, filters
    )
    assert not _snapshot_meets_required_constraints(
        {**compatible, "purpose": "rent", "sale_price": None}, filters
    )
    assert not _snapshot_meets_required_constraints(
        {**compatible, "sale_price": "1100000"}, filters
    )
