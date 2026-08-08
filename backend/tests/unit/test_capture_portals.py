from decimal import Decimal
from uuid import uuid4

from app.modules.capture.portals import build_portal_searches
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose


def test_builds_search_links_for_main_portals_including_lello() -> None:
    demand = LeadDemand(
        tenant_id=uuid4(),
        lead_name="Maria",
        phone="1",
        purpose=LeadPurpose.BUY,
        property_type="apartamento",
        city="São Paulo",
        neighborhoods=["Pinheiros"],
        price_min=Decimal("500000"),
        price_max=Decimal("900000"),
        bedrooms=2,
        parking_spaces=1,
        min_area=60,
    )

    searches = build_portal_searches(demand)

    assert [item.id for item in searches] == ["zap", "vivareal", "olx", "lello"]
    assert all(item.url.startswith("https://") for item in searches)
    assert "2-quartos" in searches[0].url
    assert "vagas=1%2C2%2C3%2C4" in searches[0].url
    assert "areaMinima=60" in searches[1].url
    assert "gsp=1" in searches[2].url and "ret=1020" in searches[2].url
    assert "pinheiros-sao_paulo-bairros" in searches[-1].url
    assert "de-500000-ate-900000-r$" in searches[-1].url
    assert "#ordenar-por-maior-valor/de-60-metros/1-vagas/" in searches[-1].url
    assert searches[2].status_message
    assert searches[-1].discovery_mode == "assisted"


def test_lello_price_route_never_uses_decimal_notation() -> None:
    demand = LeadDemand(
        tenant_id=uuid4(),
        lead_name="Bruna",
        phone="1",
        purpose=LeadPurpose.RENT,
        city="São Paulo",
        price_min=Decimal("3001.00"),
        price_max=Decimal("5000.00"),
    )

    lello = build_portal_searches(demand)[-1]

    assert "de-3001-ate-5000-r$" in lello.url
    assert ".00" not in lello.url


def test_unknown_neighborhood_is_explicitly_left_pending() -> None:
    demand = LeadDemand(
        tenant_id=uuid4(),
        lead_name="João",
        phone="1",
        purpose=LeadPurpose.RENT,
        property_type="casa",
        city="São Paulo",
        neighborhoods=["Bairro ainda não mapeado"],
    )

    searches = build_portal_searches(demand)

    assert "bairro" in searches[0].pending_filters
    assert "bairro" in searches[1].pending_filters
    assert "bairro" in searches[2].pending_filters
