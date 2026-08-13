from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode, urljoin

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


class RedeGauchaConnector(PortalConnector):
    descriptor = SourceDescriptor(
        "rede_gaucha",
        "Rede Gaúcha de Imóveis",
        "Rio Grande do Sul",
        "json_api",
    )
    parser_version = "rede-gaucha-api-v2"
    origin = "https://www.redegauchadeimoveis.com.br"
    endpoint = f"{origin}/api/frontend/real-estate-data/property/list"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city, demand.state) == "RS"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        contract = 2 if requested_purpose(demand) == "rent" else 1
        records: list[ExternalListingRecord] = []
        request_url = ""
        page = 0
        while len(records) < limit and page < 10:
            query = urlencode(
                {"contract": contract, "sort": 1, "page": page, "filter": json.dumps({})}
            )
            url = f"{self.endpoint}?{query}"
            request_url = request_url or url
            response = self.get_public(url, headers={"api-url": self.origin})
            try:
                payload = response.json()
            except ValueError as exc:
                raise SourceShapeError("A API da Rede Gaúcha retornou dados inválidos") from exc
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                raise SourceShapeError("A API da Rede Gaúcha mudou de formato")
            if not items:
                break
            candidates = [
                self._record(item, demand)
                for item in items
                if isinstance(item, dict) and item.get("id") and item.get("url")
            ]
            records.extend(
                record
                for record in candidates
                if slug(record.city) == slug(demand.city)
            )
            page += 1
        records.sort(key=lambda record: _relevance(record, demand), reverse=True)
        return ConnectorBatch(self.descriptor, self.parser_version, request_url, records[:limit])

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        coordinates = (
            address.get("coordinate") if isinstance(address.get("coordinate"), dict) else {}
        )
        contracts = item.get("contracts") if isinstance(item.get("contracts"), list) else []
        sale_price = _contract_price(contracts, 1)
        rent_price = _contract_price(contracts, 2)
        requested = requested_purpose(demand)
        price = rent_price if requested == "rent" else sale_price
        price = price or sale_price or rent_price
        images = item.get("images") if isinstance(item.get("images"), list) else []
        image = images[0] if images and isinstance(images[0], dict) else {}
        city = _text(address.get("city")) or ""
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=str(item.get("code") or item["id"]),
            canonical_url=urljoin(self.origin, str(item["url"])),
            title=_text(item.get("title")) or f"Imóvel em {city}",
            description=_text(item.get("description")),
            purpose=available_purpose(sale_price, rent_price, requested),
            property_type=_text(item.get("type")) or demand.property_type,
            state=_text(address.get("state")) or "RS",
            city=city,
            neighborhood=_text(address.get("neighborhood")),
            address={
                "street": address.get("street"),
                "number": address.get("number"),
                "complement": address.get("complement"),
                "neighborhood": address.get("neighborhood"),
                "city": city,
                "state": address.get("state") or "RS",
                "zip_code": address.get("zipCode"),
            },
            latitude=decimal_value(coordinates.get("latitude")),
            longitude=decimal_value(coordinates.get("longitude")),
            price=price,
            sale_price=sale_price,
            rent_price=rent_price,
            bedrooms=integer_value(item.get("bedrooms")),
            suites=integer_value(item.get("suites")),
            bathrooms=integer_value(item.get("bathrooms")),
            parking_spaces=integer_value(item.get("garage")),
            area=_area(item),
            land_area=integer_value(_measurement(item.get("terrainArea"))),
            primary_image_url=_text(image.get("src")),
            advertiser_name="Rede Gaúcha de Imóveis",
            raw_data={"id": item.get("id"), "code": item.get("code")},
            extraction_confidence=98,
        )


def _contract_price(contracts: list[Any], contract_id: int) -> Decimal | None:
    for contract in contracts:
        if not isinstance(contract, dict) or integer_value(contract.get("id")) != contract_id:
            continue
        price = contract.get("price") if isinstance(contract.get("price"), dict) else {}
        value = decimal_value(price.get("value"))
        return value / Decimal("100") if value is not None else None
    return None


def _area(item: dict[str, Any]) -> int | None:
    for key in ("usefulArea", "privateArea", "totalArea"):
        value = integer_value(_measurement(item.get(key)))
        if value:
            return value
    return None


def _measurement(value: Any) -> Any:
    return value.get("value") if isinstance(value, dict) else value


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
