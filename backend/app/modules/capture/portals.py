from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from app.modules.leads.domain.entities import LeadDemand
from app.modules.properties.application.matching import normalize_search_text


@dataclass(frozen=True, slots=True)
class PortalSearch:
    id: str
    name: str
    url: str
    applied_filters: list[str]
    pending_filters: list[str]
    discovery_mode: str = "manual"
    status_message: str | None = None


@dataclass(frozen=True, slots=True)
class PortalLocation:
    zone_slug: str
    neighborhood_slug: str
    zap_neighborhood_slug: str
    display_zone: str
    display_neighborhood: str
    latitude: str
    longitude: str


# Localizações confirmadas manualmente. Bairros desconhecidos permanecem como filtro pendente,
# evitando links que parecem corretos mas abrem silenciosamente outra região.
SP_LOCATIONS = {
    "pinheiros": PortalLocation(
        "zona-oeste",
        "pinheiros",
        "pinheiros",
        "Zona Oeste",
        "Pinheiros",
        "-23.563579",
        "-46.691607",
    ),
    "vila mariana": PortalLocation(
        "zona-sul",
        "vila-mariana",
        "vl-mariana",
        "Zona Sul",
        "Vila Mariana",
        "-23.589702",
        "-46.634638",
    ),
}


def build_portal_searches(demand: LeadDemand) -> list[PortalSearch]:
    return [
        _zap(demand),
        _vivareal(demand),
        _olx(demand),
        _lello(demand),
    ]


def _slug(value: str | None) -> str:
    return normalize_search_text(value).replace(" ", "-")


def _kind(value: str | None, *, plural: bool = False) -> str:
    normalized = normalize_search_text(value)
    mapping = {
        "apartamento": "apartamentos" if plural else "apartamento_residencial",
        "casa": "casas" if plural else "casa_residencial",
        "sobrado": "casas" if plural else "sobrado_residencial",
    }
    return mapping.get(normalized, "imoveis" if plural else "")


def _common_pending(demand: LeadDemand, applied: set[str]) -> list[str]:
    available = {
        "cidade": demand.city,
        "bairro": demand.neighborhoods,
        "tipo": demand.property_type,
        "preço mínimo": demand.price_min,
        "preço máximo": demand.price_max,
        "quartos": demand.bedrooms,
        "vagas": demand.parking_spaces,
        "área mínima": demand.min_area,
    }
    return [
        label
        for label, value in available.items()
        if value not in (None, [], "") and label not in applied
    ]


def _location(demand: LeadDemand) -> PortalLocation | None:
    if normalize_search_text(demand.city) != "sao paulo" or not demand.neighborhoods:
        return None
    return SP_LOCATIONS.get(normalize_search_text(demand.neighborhoods[0]))


def _range_to_four(minimum: int | None) -> str | None:
    if minimum is None:
        return None
    return ",".join(str(value) for value in range(min(minimum, 4), 5))


def _zap_viva_query(demand: LeadDemand, location: PortalLocation | None) -> dict[str, str]:
    query: dict[str, str] = {}
    if location:
        query["onde"] = (
            f",São Paulo,São Paulo,{location.display_zone},{location.display_neighborhood},,,"
            "neighborhood,BR>Sao Paulo>NULL>Sao Paulo>"
            f"{location.display_zone}>{location.display_neighborhood},"
            f"{location.latitude},{location.longitude},"
        )
    kind = _kind(demand.property_type)
    if kind:
        query["tipos"] = kind
    bedrooms = _range_to_four(demand.bedrooms)
    parking = _range_to_four(demand.parking_spaces)
    if bedrooms:
        query["quartos"] = bedrooms
    if parking:
        query["vagas"] = parking
    if demand.price_min is not None:
        query["precoMinimo"] = str(demand.price_min)
    if demand.price_max is not None:
        query["precoMaximo"] = str(demand.price_max)
    if demand.min_area is not None:
        query["areaMinima"] = str(demand.min_area)
    return query


def _zap(demand: LeadDemand) -> PortalSearch:
    purpose = "aluguel" if demand.purpose and demand.purpose.value == "rent" else "venda"
    kind = _kind(demand.property_type, plural=True)
    location = _location(demand)
    place = "sp+sao-paulo"
    if location:
        place += f"+{location.zone_slug}+{location.zap_neighborhood_slug}"
    path = f"/{purpose}/{kind}/{place}/"
    applied = {"cidade", "tipo"}
    if location:
        applied.add("bairro")
    if demand.bedrooms:
        path += f"{demand.bedrooms}-quartos/"
        applied.add("quartos")
    query = _zap_viva_query(demand, location)
    applied.update(
        label
        for label, value in {
            "preço mínimo": demand.price_min,
            "preço máximo": demand.price_max,
            "vagas": demand.parking_spaces,
            "área mínima": demand.min_area,
        }.items()
        if value is not None
    )
    url = "https://www.zapimoveis.com.br" + path + (f"?{urlencode(query)}" if query else "")
    return PortalSearch(
        "zap",
        "ZAP Imóveis",
        url,
        sorted(applied),
        _common_pending(demand, applied),
        status_message="O portal protege a leitura automática. A pesquisa abre em nova guia.",
    )


def _vivareal(demand: LeadDemand) -> PortalSearch:
    purpose = "aluguel" if demand.purpose and demand.purpose.value == "rent" else "venda"
    city = _slug(demand.city)
    kind = _kind(demand.property_type) or "imovel_residencial"
    location = _location(demand)
    location_path = f"/{location.zone_slug}/{location.neighborhood_slug}" if location else ""
    path = f"/{purpose}/sp/{city}{location_path}/{kind}/"
    applied = {"cidade", "tipo"}
    if location:
        applied.add("bairro")
    if demand.bedrooms:
        path += f"{demand.bedrooms}-quartos/"
        applied.add("quartos")
    query = _zap_viva_query(demand, location)
    applied.update(
        label
        for label, value in {
            "preço mínimo": demand.price_min,
            "preço máximo": demand.price_max,
            "vagas": demand.parking_spaces,
            "área mínima": demand.min_area,
        }.items()
        if value is not None
    )
    url = "https://www.vivareal.com.br" + path + (f"?{urlencode(query)}" if query else "")
    return PortalSearch(
        "vivareal",
        "Viva Real",
        url,
        sorted(applied),
        _common_pending(demand, applied),
        status_message="O portal protege a leitura automática. A pesquisa abre em nova guia.",
    )


def _olx(demand: LeadDemand) -> PortalSearch:
    purpose = "aluguel" if demand.purpose and demand.purpose.value == "rent" else "venda"
    path = f"/imoveis/{purpose}"
    applied = {"tipo"}
    if demand.bedrooms:
        path += f"/{demand.bedrooms}-quartos"
        applied.add("quartos")
    path += "/estado-sp/sao-paulo-e-regiao"
    location = _location(demand)
    if location:
        path += f"/{location.zone_slug}/{location.neighborhood_slug}"
    query: dict[str, str] = {}
    ret = {"apartamento": "1020", "casa": "1040", "sobrado": "1040"}.get(
        normalize_search_text(demand.property_type)
    )
    if ret:
        query["ret"] = ret
    if demand.price_min is not None:
        query["ps"] = str(demand.price_min)
    if demand.price_max is not None:
        query["pe"] = str(demand.price_max)
    if demand.parking_spaces is not None:
        query["gsp"] = str(demand.parking_spaces)
    if demand.min_area is not None:
        query["ss"] = str(demand.min_area)
    applied.update({"cidade"} if demand.city else set())
    if location:
        applied.add("bairro")
    applied.update(
        label
        for label, value in {
            "preço mínimo": demand.price_min,
            "preço máximo": demand.price_max,
            "vagas": demand.parking_spaces,
            "área mínima": demand.min_area,
        }.items()
        if value is not None
    )
    return PortalSearch(
        "olx",
        "OLX",
        "https://www.olx.com.br" + path + "?" + urlencode(query),
        sorted(applied),
        _common_pending(demand, applied),
        status_message="A OLX bloqueia consultas automáticas. Use a pesquisa assistida.",
    )


def _lello(demand: LeadDemand) -> PortalSearch:
    purpose = "aluguel" if demand.purpose and demand.purpose.value == "rent" else "venda"
    normalized_type = normalize_search_text(demand.property_type)
    type_slug = {
        "apartamento": "apartamento-tipos",
        "casa": "casa-tipos",
        "sobrado": "sobrado-tipos",
    }.get(normalized_type, "imovel-tipos")
    path = f"/{purpose}/residencial/{type_slug}"
    applied = {"tipo"}
    if demand.bedrooms:
        path += f"/{demand.bedrooms}-dormitorios"
        applied.add("quartos")
    if demand.neighborhoods and demand.city:
        neighborhood = normalize_search_text(demand.neighborhoods[0]).replace(" ", "_")
        city = normalize_search_text(demand.city).replace(" ", "_")
        path += f"/{neighborhood}-{city}-bairros"
        applied.update({"cidade", "bairro"})
    if demand.price_min is not None or demand.price_max is not None:
        # Lello's route parser rejects decimal notation (for example ``5000.00``)
        # and silently redirects to a search without the price range.
        minimum = str(int(demand.price_min or 0))
        maximum = str(int(demand.price_max or 999999999))
        path += f"/de-{minimum}-ate-{maximum}-r$"
        if demand.price_min is not None:
            applied.add("preço mínimo")
        if demand.price_max is not None:
            applied.add("preço máximo")
    path += "/1-pagina"
    fragments = ["ordenar-por-maior-valor"]
    if demand.min_area is not None:
        fragments.append(f"de-{demand.min_area}-metros")
        applied.add("área mínima")
    if demand.parking_spaces is not None:
        fragments.append(f"{demand.parking_spaces}-vagas")
        applied.add("vagas")
    url = "https://www.lelloimoveis.com.br" + path + "/#" + "/".join(fragments) + "/"
    return PortalSearch(
        "lello",
        "Lello Imóveis",
        url,
        sorted(applied),
        _common_pending(demand, applied),
        discovery_mode="assisted",
        status_message="A busca abre no portal; confirme os filtros antes de salvar anúncios.",
    )
