from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlencode, urljoin

from app.modules.capture.connectors.base import (
    ConnectorBatch,
    ExternalListingRecord,
    PortalConnector,
    SourceDescriptor,
    SourceShapeError,
    decimal_value,
    infer_state,
    integer_value,
    requested_purpose,
    slug,
)
from app.modules.leads.domain.entities import LeadDemand


class DapperConnector(PortalConnector):
    descriptor = SourceDescriptor(
        "dapper",
        "Dapper Imóveis",
        "Rio Grande do Sul",
        "json_api",
    )
    parser_version = "dapper-api-v1"
    origin = "https://dapperimoveis.com.br"
    endpoint = f"{origin}/Services/RealEstate/JSONP/List.aspx"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city, demand.state) == "RS"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        purpose = requested_purpose(demand)
        negotiation_type = 1 if purpose == "rent" else 2
        params: dict[str, str | int] = {
            "mode": "realties",
            "callback": "null",
            "nt": negotiation_type,
            "tipo_negociacao": negotiation_type,
            "ordem": 2,
            "pageSize": max(1, limit),
        }
        if demand.city:
            params["cidade"] = demand.city
        if demand.neighborhoods:
            params["bairros"] = ",".join(demand.neighborhoods)
        if demand.bedrooms:
            params["dormitorios"] = demand.bedrooms
        if demand.parking_spaces:
            params["vagas"] = demand.parking_spaces
        if demand.price_min is not None:
            params["valor_de"] = int(demand.price_min)
        if demand.price_max is not None:
            params["valor_ate"] = int(demand.price_max)
        realty_type = _realty_type_id(demand.property_type)
        if realty_type:
            params["tipo_imovel"] = realty_type

        url = f"{self.endpoint}?{urlencode(params)}"
        response = self.get_public(url, headers={"Accept": "application/json"})
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceShapeError("A Dapper retornou dados inválidos") from exc
        if not isinstance(payload, dict) or payload.get("Error") is True:
            raise SourceShapeError("A consulta pública da Dapper mudou de formato")
        items = payload.get("Items")
        if not isinstance(items, list):
            raise SourceShapeError("A consulta pública da Dapper não contém imóveis")

        records = [
            self._record(item, demand)
            for item in items[:limit]
            if isinstance(item, dict) and item.get("Id")
        ]
        records.sort(key=lambda record: _relevance(record, demand), reverse=True)
        return ConnectorBatch(self.descriptor, self.parser_version, str(response.url), records)

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        spot = item.get("CurrentSpot") if isinstance(item.get("CurrentSpot"), dict) else {}
        negotiation_type = integer_value(item.get("CurrentNegotiationTypeId"))
        raw_price = _positive_decimal(item.get("Price"))
        sale_price = raw_price if negotiation_type == 2 else None
        rent_price = raw_price if negotiation_type == 1 else None
        preferred_price = rent_price if requested_purpose(demand) == "rent" else sale_price
        city = _text(spot.get("City")) or demand.city or "Novo Hamburgo"
        state = _text(spot.get("CurrentStateName")) or "RS"
        neighborhood = _text(spot.get("Neighborhood"))
        reference = _text(item.get("ReferenceId")) or str(item["Id"])
        photos = item.get("Photos") if isinstance(item.get("Photos"), list) else []
        first_photo = photos[0] if photos and isinstance(photos[0], dict) else {}
        image_path = _text(first_photo.get("Path")) or _text(item.get("Image"))

        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=str(item["Id"]),
            canonical_url=f"{self.origin}/imovel/{quote(reference, safe='')}",
            title=_text(item.get("Title")) or f"Imóvel em {city}",
            description=_text(item.get("Description")) or _text(item.get("Abstract")),
            purpose="rent" if negotiation_type == 1 else "buy",
            property_type=_text(item.get("CurrentRealtyTypeTitle")) or demand.property_type,
            state=state,
            city=city,
            neighborhood=neighborhood,
            address={
                "street": _text(spot.get("CurrentAddress")),
                "number": _text(spot.get("Number")),
                "complement": _text(spot.get("Complement")),
                "neighborhood": neighborhood,
                "city": city,
                "state": state,
                "zip_code": _text(spot.get("ZipCode")),
            },
            latitude=_coordinate(spot.get("Latitude"), Decimal("90")),
            longitude=_coordinate(spot.get("Longitude"), Decimal("180")),
            price=preferred_price or sale_price or rent_price,
            sale_price=sale_price,
            rent_price=rent_price,
            condominium_fee=_positive_decimal(item.get("CondominiumValue")),
            property_tax=_positive_decimal(item.get("IPTUValue")),
            bedrooms=_positive_integer(item.get("Bedrooms")),
            suites=_positive_integer(item.get("Suites")),
            bathrooms=_positive_integer(item.get("Bathrooms")),
            parking_spaces=_positive_integer(item.get("ParkingSpots")),
            area=_positive_integer(item.get("Area") or item.get("FormattedArea")),
            land_area=_positive_integer(item.get("LotArea") or item.get("FormattedLotArea")),
            primary_image_url=urljoin(f"{self.origin}/", image_path) if image_path else None,
            advertiser_name="Dapper Imóveis",
            advertiser_phone=_text(item.get("AgencyCellphone")),
            raw_data={"id": item.get("Id"), "reference": reference},
            extraction_confidence=98,
        )


_REALTY_TYPE_IDS = {
    "apartamento": "50",
    "area": "58",
    "box": "63",
    "box-garagem": "63",
    "garagem": "63",
    "casa": "54",
    "sobrado": "54",
    "casa-em-condominio": "62",
    "condominio": "62",
    "chacara": "59",
    "sitio": "59",
    "chale": "55",
    "cobertura": "61",
    "conjunto-residencial": "64",
    "hotel": "66",
    "jk": "53",
    "kitnet": "53",
    "kitchenette": "53",
    "loft": "65",
    "loja": "51",
    "pavilhao": "49",
    "deposito": "49",
    "ponto-comercial": "67",
    "predio-comercial": "57",
    "sala-comercial": "52",
    "terreno": "48",
    "terreno-em-condominio": "60",
}


def _realty_type_id(value: str | None) -> str | None:
    normalized = slug(value)
    if normalized in _REALTY_TYPE_IDS:
        return _REALTY_TYPE_IDS[normalized]
    for candidate, realty_type in _REALTY_TYPE_IDS.items():
        if candidate in normalized or normalized in candidate:
            return realty_type
    return None


def _positive_decimal(value: Any) -> Decimal | None:
    parsed = decimal_value(value)
    return parsed if parsed is not None and parsed > 0 else None


def _positive_integer(value: Any) -> int | None:
    parsed = integer_value(value)
    return parsed if parsed is not None and parsed > 0 else None


def _coordinate(value: Any, maximum: Decimal) -> Decimal | None:
    parsed = decimal_value(value)
    if parsed is None:
        return None
    while abs(parsed) > maximum:
        parsed /= Decimal("10")
    return parsed


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
            and slug(demand.property_type) in slug(record.property_type)
        )
    )
    return city, neighborhood, property_type


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
