from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

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
)
from app.modules.leads.domain.entities import LeadDemand


class ImoveisDiferenciadosConnector(PortalConnector):
    descriptor = SourceDescriptor("imoveis_diferenciados", "Imóveis Diferenciados", "Bahia", "json")
    parser_version = "imoveis-diferenciados-api-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city) == "BA"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        purpose = requested_purpose(demand)
        params = {
            "limit": limit,
            "offset": 1,
            "custom_query": "card",
            "filter[transaction]": 2 if purpose == "rent" else 1,
        }
        url = "https://api-sites.tecimob.com.br/api/properties?" + urlencode(params)
        response = self.get_public(
            url,
            headers={
                "Accept": "application/json",
                "x-domain": "imoveisdiferenciados.com.br",
            },
        )
        try:
            items = response.json()["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceShapeError("A API de Imóveis Diferenciados mudou de formato") from exc
        if not isinstance(items, list):
            raise SourceShapeError("A API de Imóveis Diferenciados não retornou uma lista")
        records = [self._record(item, demand) for item in items[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        neighborhood, city, state = _location(str(address.get("formatted") or ""))
        rooms = item.get("rooms") if isinstance(item.get("rooms"), dict) else {}
        areas = item.get("areas") if isinstance(item.get("areas"), dict) else {}
        images = item.get("images") if isinstance(item.get("images"), list) else []
        image = images[0] if images and isinstance(images[0], dict) else {}
        file_url = image.get("file_url") if isinstance(image.get("file_url"), dict) else {}
        purpose = requested_purpose(demand)
        price = decimal_value(item.get("price"))
        path = str(item.get("url") or "").lstrip("/")
        canonical_url = f"https://imoveisdiferenciados.com.br/imovel/{path}"
        property_type = _property_type(str(item.get("meta_title") or ""))
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=str(item.get("reference") or item.get("id")),
            canonical_url=canonical_url,
            title=str(item.get("title_formatted") or item.get("meta_title") or "Imóvel"),
            purpose=purpose,
            property_type=property_type or demand.property_type,
            state=state or infer_state(city) or infer_state(demand.city),
            city=city or str(demand.city or ""),
            neighborhood=neighborhood,
            address={
                "neighborhood": neighborhood,
                "city": city or demand.city,
                "state": state or infer_state(city) or infer_state(demand.city),
            },
            price=price,
            sale_price=price if purpose == "buy" else None,
            rent_price=price if purpose == "rent" else None,
            bedrooms=_room(rooms, "bedroom"),
            suites=_room(rooms, "suite"),
            bathrooms=_room(rooms, "bathroom"),
            parking_spaces=_room(rooms, "garage"),
            area=_area(areas),
            primary_image_url=_text(file_url.get("medium") or file_url.get("large")),
            advertiser_name="Imóveis Diferenciados",
            raw_data={"api_id": item.get("id"), "transaction": item.get("transaction")},
            extraction_confidence=96,
        )


def _location(value: str) -> tuple[str | None, str | None, str | None]:
    match = re.match(r"\s*(.*?)\s+-\s+(.*?)/([A-Z]{2})\s*$", value, re.I)
    return match.groups() if match else (None, None, None)


def _room(rooms: dict[str, Any], name: str) -> int | None:
    value = rooms.get(name)
    return integer_value(value.get("value")) if isinstance(value, dict) else None


def _area(areas: dict[str, Any]) -> int | None:
    for name in ("primary_area", "private_area", "total_area"):
        value = areas.get(name)
        if isinstance(value, dict) and value.get("value") not in (None, ""):
            return integer_value(value.get("value"))
    return None


def _property_type(value: str) -> str | None:
    match = re.match(r"(.+?)(?:\s+à venda|\s+para alugar|\s+-)", value, re.I)
    return match.group(1).strip() if match else None


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
