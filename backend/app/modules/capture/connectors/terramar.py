from __future__ import annotations

import html as html_module
import re
from urllib.parse import urlsplit

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


class TerramarConnector(PortalConnector):
    descriptor = SourceDescriptor("terramar", "Terramar Imóveis", "Rio Grande do Sul", "html")
    parser_version = "terramar-html-v2"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city, demand.state) == "RS"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        purpose = requested_purpose(demand)
        action = "aluguel" if purpose == "rent" else "venda"
        property_type = slug(demand.property_type) or "residencial_comercial"
        url = f"https://terramar.com.br/{action}/{property_type}/{slug(demand.city)}/"
        if demand.bedrooms:
            url += f"{demand.bedrooms}-dormitorios/"
        response = self.get_public(url)
        cards = _cards(response.text)
        if not cards and urlsplit(str(response.url)).path.rstrip("/") in {"", "/"}:
            return ConnectorBatch(
                self.descriptor,
                self.parser_version,
                str(response.url),
                [],
                metadata={"empty_reason": "city_outside_catalog"},
            )
        records = [self._record(card, demand) for card in cards[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, str(response.url), records)

    def _record(self, card: str, demand: LeadDemand) -> ExternalListingRecord:
        code_match = re.search(r'\bdata-codigo=["\']([^"\']+)', card, re.I)
        url_match = re.search(r'<a\b[^>]*href=["\']([^"\']+/imovel/[^"\']+)', card, re.I)
        if not code_match or not url_match:
            raise SourceShapeError("A Terramar não informou o código do imóvel")
        code = code_match.group(1)
        canonical_url = html_module.unescape(url_match.group(1))
        title = _element_text(card, "h2", "titulo-grid") or "Imóvel Terramar"
        address_html = _street_address(card) or ""
        address_without_building = address_html.split("<small", 1)[0]
        address_text = _clean_text(address_without_building)
        city = _city(address_text) or ""
        neighborhood = _neighborhood(address_text, city)
        prices = _prices(card)
        sale_price = prices.get("buy")
        rent_price = prices.get("rent")
        purpose = available_purpose(sale_price, rent_price, requested_purpose(demand))
        preferred = rent_price if requested_purpose(demand) == "rent" else sale_price
        price = preferred or sale_price or rent_price
        image_match = re.search(r"background-image\s*:\s*url\(([^)]+)\)", card, re.I)
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=code,
            canonical_url=canonical_url,
            title=title,
            purpose=purpose,
            property_type=(title.split(" ", 1)[0] or demand.property_type).strip(),
            state="RS",
            city=city,
            neighborhood=neighborhood,
            address={
                "formatted": address_text or None,
                "neighborhood": neighborhood,
                "city": city,
                "state": "RS",
            },
            price=price,
            sale_price=sale_price,
            rent_price=rent_price,
            condominium_fee=decimal_value(_labeled_price(card, "Condomínio")),
            bedrooms=_amenity(card, "Quartos"),
            suites=_amenity(card, "Suítes"),
            parking_spaces=_amenity(card, "Vagas"),
            area=_amenity(card, "Privat"),
            primary_image_url=(
                html_module.unescape(image_match.group(1).strip(" \"'")) if image_match else None
            ),
            advertiser_name="Terramar Imóveis",
            raw_data={"code": code},
            extraction_confidence=93,
        )


def _cards(value: str) -> list[str]:
    matches = list(
        re.finditer(r'<div\b(?=[^>]*class=["\'][^"\']*\bimovel-box-single\b)[^>]*>', value, re.I)
    )
    return [
        value[
            match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(value)
        ]
        for index, match in enumerate(matches)
    ]


def _prices(card: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for match in re.finditer(
        r"thumb-status[^>]*>(.*?)</span>.*?thumb-price[^>]*>(.*?)</span>",
        card,
        re.I | re.S,
    ):
        label = _clean_text(match.group(1)).casefold()
        price = decimal_value(_clean_text(match.group(2)))
        if price is not None:
            values["rent" if "alug" in label or "loca" in label else "buy"] = price
    return values


def _labeled_price(card: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\s*(R\$\s*[\d.,]+)", _clean_text(card), re.I)
    return match.group(1) if match else None


def _amenity(card: str, label: str) -> int | None:
    match = re.search(
        rf"<span[^>]*>((?:(?!<span\b).)*?)</span>\s*<small[^>]*>\s*{re.escape(label)}",
        card,
        re.I | re.S,
    )
    return integer_value(_clean_text(match.group(1))) if match else None


def _street_address(value: str) -> str | None:
    match = re.search(
        r'<h3\b[^>]*itemprop=["\']streetAddress["\'][^>]*>(.*?)</h3>',
        value,
        re.I | re.S,
    )
    return match.group(1) if match else None


def _element_html(value: str, tag: str, class_name: str) -> str | None:
    match = re.search(
        rf'<{tag}\b[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>(.*?)</{tag}>',
        value,
        re.I | re.S,
    )
    return match.group(1) if match else None


def _element_text(value: str, tag: str, class_name: str) -> str | None:
    body = _element_html(value, tag, class_name)
    return _clean_text(body) if body is not None else None


def _clean_text(value: str) -> str:
    return " ".join(html_module.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _city(value: str) -> str | None:
    match = re.search(r"-\s*([^/]+)\s*/\s*RS", value, re.I)
    return match.group(1).strip() if match else None


def _neighborhood(value: str, city: str) -> str | None:
    before_city = re.split(rf"\s*-\s*{re.escape(city)}\b", value, maxsplit=1, flags=re.I)[0]
    parts = [part.strip() for part in before_city.split(",") if part.strip()]
    return parts[-1] if len(parts) >= 2 else None
