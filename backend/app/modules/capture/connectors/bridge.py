from __future__ import annotations

import html as html_module
import re
from typing import Any

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
from app.modules.capture.connectors.html import json_documents, walk_json
from app.modules.leads.domain.entities import LeadDemand


class BridgeConnector(PortalConnector):
    descriptor = SourceDescriptor("bridge", "Bridge Imóveis", "Rio Grande do Sul", "json_ld")
    parser_version = "bridge-jsonld-v2"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city, demand.state) == "RS"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        action = "alugar" if requested_purpose(demand) == "rent" else "comprar"
        url = f"https://www.bridgeimoveis.com.br/busca/{action}"
        response = self.get_public(url)
        products = _products(response.text)
        records = [self._record(item, demand, response.text) for item in products]
        records = [
            record
            for record in records
            if slug(record.city) == slug(demand.city)
        ][:limit]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, item: dict[str, Any], demand: LeadDemand, html: str) -> ExternalListingRecord:
        name = str(item.get("name") or "Imóvel Bridge")
        code = _code_from_name(name)
        offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
        seller = offers.get("seller") if isinstance(offers.get("seller"), dict) else {}
        purpose = requested_purpose(demand) or "buy"
        price = decimal_value(offers.get("price"))
        description = _text(item.get("description"))
        neighborhood = _neighborhood_from_name(name)
        city = _city_from_name(name)
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=code,
            canonical_url=_canonical_url(html, code),
            title=name,
            description=description,
            purpose=purpose,
            property_type=name.split(",", 1)[0].strip() or demand.property_type,
            state="RS",
            city=city,
            neighborhood=neighborhood,
            address={
                "neighborhood": neighborhood,
                "city": city,
                "state": "RS",
            },
            price=price,
            sale_price=price if purpose == "buy" else None,
            rent_price=price if purpose == "rent" else None,
            bedrooms=_number_in_text(description, r"(\d+)\s+(?:dormit[oó]rios?|quartos?)"),
            suites=_number_in_text(description, r"(\d+)\s+su[ií]tes?"),
            bathrooms=_number_in_text(description, r"(\d+)\s+banheiros?"),
            parking_spaces=_number_in_text(description, r"(\d+)\s+vagas?"),
            area=_number_in_text(name, r"([\d.,]+)\s*m[²2]"),
            primary_image_url=_image(item.get("image")),
            advertiser_name=_text(seller.get("name")) or "Bridge Imóveis",
            advertiser_phone=_text(seller.get("telephone")),
            raw_data={"code": code, "availability": offers.get("availability")},
            extraction_confidence=91,
        )


def _products(html: str) -> list[dict[str, Any]]:
    for document in json_documents(html):
        values = [
            value
            for value in walk_json(document)
            if isinstance(value, dict)
            and value.get("@type") == "Product"
            and isinstance(value.get("offers"), dict)
            and _code_from_name(str(value.get("name") or ""), required=False)
        ]
        if values:
            return values
    raise SourceShapeError("A busca da Bridge não contém imóveis estruturados")


def _code_from_name(value: str, *, required: bool = True) -> str:
    match = re.search(r"-\s*(\d{3,})\s*$", value)
    if match:
        return match.group(1)
    if required:
        raise SourceShapeError("A Bridge não informou o código do imóvel")
    return ""


def _canonical_url(html: str, code: str) -> str:
    match = re.search(
        rf'data-url=["\']([^"\']+/imovel/{re.escape(code)}(?:/[^"\']*)?)["\']', html, re.I
    )
    return (
        html_module.unescape(match.group(1))
        if match
        else f"https://www.bridgeimoveis.com.br/imovel/{code}"
    )


def _neighborhood_from_name(value: str) -> str | None:
    match = re.search(r"-\s*([^,]+),\s*(?:POA|Porto Alegre)/RS\s*-", value, re.I)
    return match.group(1).strip() if match else None


def _city_from_name(value: str) -> str:
    match = re.search(r",\s*([^,/]+)\s*/\s*RS\s*-", value, re.I)
    if not match:
        return ""
    city = match.group(1).strip()
    return "Porto Alegre" if city.casefold() == "poa" else city


def _number_in_text(value: str | None, pattern: str) -> int | None:
    match = re.search(pattern, value or "", re.I)
    return integer_value(match.group(1)) if match else None


def _image(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return _text(value)


def _text(value: object) -> str | None:
    return str(value).strip() if value not in (None, "") else None
