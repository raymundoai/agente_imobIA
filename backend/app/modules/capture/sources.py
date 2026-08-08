from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from app.modules.leads.domain.entities import LeadDemand


@dataclass(frozen=True, slots=True)
class FederatedSource:
    id: str
    name: str
    domain: str
    coverage: str
    source_type: str = "portal"
    partnership_friendly: bool = False


# Registry deliberately contains only public discovery targets. An authenticated source must
# enter through a formal integration and must never be scraped with a user's credentials.
SOURCES = (
    FederatedSource("spimovel", "SP Imóvel", "spimovel.com.br", "São Paulo"),
    FederatedSource("lopes", "Lopes", "lopes.com.br", "Nacional"),
    FederatedSource("imovelweb", "Imovelweb", "imovelweb.com.br", "Nacional"),
    FederatedSource("chavesnamao", "Chaves na Mão", "chavesnamao.com.br", "Nacional"),
    FederatedSource("loft", "Loft", "loft.com.br", "São Paulo e grandes capitais"),
    FederatedSource("portalcreci", "Portal CRECI", "portalcreci.org.br", "Nacional"),
    FederatedSource("dfimoveis", "DF Imóveis", "dfimoveis.com.br", "Distrito Federal"),
    FederatedSource("imoveissc", "Imóveis SC", "imoveis-sc.com.br", "Santa Catarina"),
    FederatedSource(
        "curitiba", "Portal Imóveis Curitiba", "portalimoveiscuritiba.com.br", "Curitiba"
    ),
    FederatedSource("rjimoveis", "Portal RJ Imóveis", "portalrjimoveis.com.br", "Rio de Janeiro"),
    FederatedSource("mgfimoveis", "MGF Imóveis", "mgfimoveis.com.br", "Nacional"),
    FederatedSource("fastsale", "Fast Sale", "fastsaleimoveis.com.br", "Nacional", "network", True),
    FederatedSource(
        "corretores", "Corretores.com.br", "corretores.com.br", "Nacional", "network", True
    ),
    FederatedSource(
        "fiftybrasil", "FiftyBrasil", "fiftybrasil.com.br", "Nacional", "network", True
    ),
    FederatedSource("vendejunto", "Vende Junto", "vendejunto.com.br", "Nacional", "network", True),
    FederatedSource("imobishare", "ImobiShare", "imobishare.com.br", "Nacional", "network", True),
)


def build_federated_sources(demand: LeadDemand) -> list[dict[str, object]]:
    query = _query(demand)
    return [
        {
            "id": source.id,
            "name": source.name,
            "domain": source.domain,
            "coverage": source.coverage,
            "source_type": source.source_type,
            "partnership_friendly": source.partnership_friendly,
            "search_url": "https://www.google.com/search?"
            + urlencode({"q": f"site:{source.domain} {query}"}),
        }
        for source in SOURCES
        if _is_relevant(source, demand)
    ]


def _query(demand: LeadDemand) -> str:
    parts = [
        "imóvel",
        "aluguel" if demand.purpose and demand.purpose.value == "rent" else "venda",
        demand.property_type or "",
        demand.city or "",
        " ".join(demand.neighborhoods),
        f"{demand.bedrooms} quartos" if demand.bedrooms else "",
        f"{demand.parking_spaces} vagas" if demand.parking_spaces else "",
        f"até R$ {int(demand.price_max)}" if demand.price_max is not None else "",
    ]
    return " ".join(part for part in parts if part)


def _is_relevant(source: FederatedSource, demand: LeadDemand) -> bool:
    if source.coverage in {"Nacional", "São Paulo e grandes capitais"}:
        return True
    city = (demand.city or "").casefold()
    coverage = source.coverage.casefold()
    if "são paulo" in city:
        return "são paulo" in coverage
    if "rio de janeiro" in city:
        return "rio de janeiro" in coverage
    if "curitiba" in city:
        return "curitiba" in coverage
    return not city
