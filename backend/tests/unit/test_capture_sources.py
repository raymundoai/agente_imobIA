from decimal import Decimal
from uuid import uuid4

from app.modules.capture.sources import build_federated_sources
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose


def test_builds_regional_and_partnership_searches_from_demand() -> None:
    demand = LeadDemand(
        tenant_id=uuid4(),
        lead_name="Felipe",
        phone="1",
        purpose=LeadPurpose.BUY,
        property_type="casa",
        city="São Paulo",
        price_max=Decimal("1000000"),
        bedrooms=2,
        parking_spaces=1,
    )

    sources = build_federated_sources(demand)
    ids = {item["id"] for item in sources}

    assert "spimovel" in ids
    assert "dfimoveis" not in ids
    assert "fastsale" in ids
    assert next(item for item in sources if item["id"] == "fastsale")[
        "partnership_friendly"
    ]
    assert all("google.com/search?" in str(item["search_url"]) for item in sources)
    assert "2+quartos" in str(sources[0]["search_url"])


def test_unknown_city_keeps_only_national_sources() -> None:
    demand = LeadDemand(
        tenant_id=uuid4(),
        lead_name="Ana",
        phone="1",
        purpose=LeadPurpose.RENT,
        city="Porto Alegre",
    )

    sources = build_federated_sources(demand)

    assert sources
    assert all(item["coverage"] in {"Nacional", "São Paulo e grandes capitais"} for item in sources)
