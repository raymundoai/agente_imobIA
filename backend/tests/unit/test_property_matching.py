from decimal import Decimal
from uuid import uuid4

from app.modules.leads.domain.entities import LeadDemand, LeadPurpose
from app.modules.properties.application.matching import (
    calculate_property_match,
    meets_required_constraints,
    property_offer_price,
)
from app.modules.properties.domain.entities import Property, PropertyPurpose


def test_match_normalizes_text_supports_both_and_uses_rent_price() -> None:
    tenant_id = uuid4()
    demand = LeadDemand(
        tenant_id=tenant_id,
        lead_name="Maria",
        phone="5511999999999",
        purpose=LeadPurpose.RENT,
        city="Sao Paulo",
        neighborhoods=["Vila Olímpia"],
        property_type="Apartamento",
        price_max=Decimal("5000"),
        bedrooms=2,
        parking_spaces=1,
        min_area=60,
    )
    property_ = Property(
        tenant_id=tenant_id,
        source="manual",
        title="Apartamento",
        city="São Paulo",
        neighborhood="Vila Olimpia",
        purpose=PropertyPurpose.BOTH,
        property_type="apartamento residencial",
        sale_price=Decimal("1000000"),
        rent_price=Decimal("4500"),
        bedrooms=2,
        parking_spaces=1,
        area=65,
    )

    match = calculate_property_match(property_, demand)

    assert match.score == 100
    assert property_offer_price(property_, "rent") == Decimal("4500")
    assert match.tradeoffs == []


def test_match_explains_tradeoffs() -> None:
    tenant_id = uuid4()
    demand = LeadDemand(
        tenant_id=tenant_id,
        lead_name="João",
        phone="1",
        purpose=LeadPurpose.BUY,
        city="São Paulo",
        neighborhoods=["Pinheiros"],
        price_max=Decimal("800000"),
    )
    property_ = Property(
        tenant_id=tenant_id,
        source="manual",
        title="Casa",
        city="São Paulo",
        neighborhood="Moema",
        purpose=PropertyPurpose.BUY,
        sale_price=Decimal("900000"),
    )

    match = calculate_property_match(property_, demand)

    assert match.score < 100
    assert "fora dos bairros preferidos" in match.tradeoffs
    assert "fora da faixa de preço" in match.tradeoffs


def test_required_constraints_reject_wrong_city_purpose_and_price() -> None:
    tenant_id = uuid4()
    demand = LeadDemand(
        tenant_id=tenant_id,
        lead_name="João",
        phone="1",
        purpose=LeadPurpose.RENT,
        city="São Leopoldo",
        state="RS",
        price_max=Decimal("5000"),
    )
    compatible = Property(
        tenant_id=tenant_id,
        source="portal",
        title="Casa",
        city="Sao Leopoldo",
        purpose=PropertyPurpose.BOTH,
        rent_price=Decimal("4500"),
        address={"state": "RS"},
    )
    wrong_city = Property(
        tenant_id=tenant_id,
        source="portal",
        title="Casa",
        city="Porto Alegre",
        purpose=PropertyPurpose.RENT,
        rent_price=Decimal("4500"),
    )
    over_budget = Property(
        tenant_id=tenant_id,
        source="portal",
        title="Casa",
        city="São Leopoldo",
        purpose=PropertyPurpose.RENT,
        rent_price=Decimal("6000"),
    )

    assert meets_required_constraints(compatible, demand)
    assert not meets_required_constraints(wrong_city, demand)
    assert not meets_required_constraints(over_budget, demand)
