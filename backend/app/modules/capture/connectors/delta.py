from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import urljoin

from app.modules.capture.connectors.base import (
    ConnectorBatch,
    ExternalListingRecord,
    PortalConnector,
    SourceDescriptor,
    SourceShapeError,
    available_purpose,
    decimal_value,
    infer_state,
    integer_value,
    requested_purpose,
    slug,
)
from app.modules.leads.domain.entities import LeadDemand


class DeltaConnector(PortalConnector):
    descriptor = SourceDescriptor(
        "delta",
        "Delta Imobiliária",
        "Rio Grande do Sul",
        "graphql",
    )
    parser_version = "delta-graphql-v2"
    origin = "https://deltaimobiliariars.com.br"
    endpoint = f"{origin}/api/gql"
    codsite = "1939"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city, demand.state) == "RS"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        records: list[ExternalListingRecord] = []
        pages = min(2, max(1, (limit + 11) // 12))
        for page in range(1, pages + 1):
            query = _query(demand, page)
            response = self.post_public(
                self.endpoint,
                json={"query": query},
                headers={
                    "dominion": self.origin,
                    "x-graphql-client-name": self.origin,
                    "codsite": self.codsite,
                },
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise SourceShapeError("A Delta retornou dados inválidos") from exc
            if payload.get("errors") and not payload.get("data"):
                raise SourceShapeError("A consulta pública da Delta mudou de formato")
            result = (payload.get("data") or {}).get("imoveis_busca")
            items = result.get("imoveis") if isinstance(result, dict) else None
            if not isinstance(items, list):
                raise SourceShapeError("A consulta pública da Delta não contém imóveis")
            if not items:
                break
            candidates = [
                self._record(item, demand)
                for item in items
                if isinstance(item, dict) and item.get("id")
            ]
            records.extend(
                record
                for record in candidates
                if slug(record.city) == slug(demand.city)
            )
        records.sort(key=lambda record: _relevance(record, demand), reverse=True)
        return ConnectorBatch(self.descriptor, self.parser_version, self.endpoint, records[:limit])

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        city_data = item.get("cidade") if isinstance(item.get("cidade"), dict) else {}
        neighborhood_data = item.get("bairro") if isinstance(item.get("bairro"), dict) else {}
        type_data = item.get("tipo") if isinstance(item.get("tipo"), dict) else {}
        city = _text(city_data.get("nome")) or ""
        neighborhood = _text(neighborhood_data.get("nome"))
        property_type = _text(type_data.get("nome")) or demand.property_type
        sale_price = _positive_price(item.get("preco_venda")) if item.get("venda") else None
        rent_price = _positive_price(item.get("preco_locacao")) if item.get("aluguel") else None
        special = item.get("preco_especial") if isinstance(item.get("preco_especial"), dict) else {}
        sale_price = _positive_price(special.get("preco_especial_venda")) or sale_price
        rent_price = _positive_price(special.get("preco_especial_locacao")) or rent_price
        requested = requested_purpose(demand)
        price = rent_price if requested == "rent" else sale_price
        price = price or sale_price or rent_price
        photo = _photo(item.get("fotos"))
        action = "aluguel" if requested == "rent" else "venda"
        reference = str(item.get("referencia") or item["id"])
        path = "/".join(
            (
                "imoveis",
                action,
                slug(city) or "-",
                slug(neighborhood) or "-",
                "-",
                slug(property_type) or "imovel",
                reference,
                "imovel",
                str(item["id"]),
            )
        )
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=str(item["id"]),
            canonical_url=urljoin(f"{self.origin}/", path),
            title=_text(item.get("titulo")) or f"{property_type or 'Imóvel'} em {city}",
            description=_text(item.get("descricao")),
            purpose=available_purpose(sale_price, rent_price, requested),
            property_type=property_type,
            state="RS",
            city=city,
            neighborhood=neighborhood,
            address={
                "neighborhood": neighborhood,
                "city": city,
                "state": "RS",
            },
            price=price,
            sale_price=sale_price,
            rent_price=rent_price,
            bedrooms=integer_value(item.get("dormitorios")),
            suites=integer_value(item.get("suites")),
            bathrooms=integer_value(item.get("banheiros")),
            parking_spaces=integer_value(item.get("garagems")),
            area=_area(item),
            land_area=integer_value(item.get("terreno")),
            primary_image_url=photo,
            advertiser_name="Delta Imobiliária",
            raw_data={"id": item.get("id"), "reference": reference},
            extraction_confidence=98,
        )


def _query(demand: LeadDemand, page: int) -> str:
    purpose = requested_purpose(demand)
    arguments = [f"pagina: {int(page)}", "ordenar: Inclusao", "ordem: desc"]
    arguments.append("aluguel: 1" if purpose == "rent" else "venda: 1")
    if demand.bedrooms:
        arguments.extend(
            (
                f"dormitorios_min: {int(demand.bedrooms)}",
                f"dormitorios_max: {int(demand.bedrooms)}",
            )
        )
    if demand.parking_spaces:
        arguments.extend(
            (
                f"garagems_min: {int(demand.parking_spaces)}",
                f"garagems_max: {int(demand.parking_spaces)}",
            )
        )
    if demand.min_area:
        arguments.append(f"metragem_min: {int(demand.min_area)}")
    if demand.price_min:
        field = "preco_locacao_min" if purpose == "rent" else "preco_venda_min"
        arguments.append(f"{field}: {int(demand.price_min)}")
    if demand.price_max:
        field = "preco_locacao_max" if purpose == "rent" else "preco_venda_max"
        arguments.append(f"{field}: {int(demand.price_max)}")
    query = """
    {
      imoveis_busca(__ARGUMENTS__) {
        count
        imoveis {
          id referencia titulo descricao venda aluguel
          tipo { nome id }
          categoria { nome id }
          cidade { nome id }
          bairro { nome id }
          dormitorios suites banheiros garagems
          preco_venda preco_locacao
          area_total area_privativa area_util terreno
          fotos { url_foto }
          preco_especial { preco_especial_venda preco_especial_locacao }
        }
      }
    }
    """
    return query.replace("__ARGUMENTS__", ", ".join(arguments))


def _positive_price(value: Any) -> Decimal | None:
    parsed = decimal_value(value)
    return parsed if parsed is not None and parsed > 0 else None


def _area(item: dict[str, Any]) -> int | None:
    for key in ("area_util", "area_privativa", "area_total"):
        value = integer_value(item.get(key))
        if value:
            return value
    return None


def _photo(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        return _text(value.get("url_foto"))
    return None


def _relevance(record: ExternalListingRecord, demand: LeadDemand) -> tuple[int, int, int]:
    city = int(bool(demand.city and record.city.casefold() == demand.city.casefold()))
    neighborhoods = {value.casefold() for value in demand.neighborhoods}
    neighborhood = int(
        bool(record.neighborhood and record.neighborhood.casefold() in neighborhoods)
    )
    property_type = int(
        bool(
            demand.property_type
            and record.property_type
            and demand.property_type.casefold() in record.property_type.casefold()
        )
    )
    return city, neighborhood, property_type


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
