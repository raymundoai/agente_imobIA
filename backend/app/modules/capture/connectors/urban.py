from __future__ import annotations

import html as html_module
import re

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


class UrbanConnector(PortalConnector):
    descriptor = SourceDescriptor("urban", "Urban Company", "Rio Grande do Sul", "html")
    parser_version = "urban-html-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return (
            infer_state(demand.city, demand.state) == "RS"
            and requested_purpose(demand) != "rent"
        )

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        parts = ["https://www.urban.imb.br/buscar/comprar"]
        if demand.property_type:
            parts.append(slug(demand.property_type))
        parts.append(f"na-cidade-de-{slug(demand.city)}")
        if demand.bedrooms:
            parts.append(f"{demand.bedrooms}-dormitorios")
        url = "/".join(parts)
        response = self.get_public(url)
        cards = _cards(response.text)
        records = [self._record(card, demand) for card in cards[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, str(response.url), records)

    def _record(self, card: str, demand: LeadDemand) -> ExternalListingRecord:
        opening = re.search(r"<a\b[^>]*\bproperty-listing\b[^>]*>", card, re.I)
        if not opening:
            raise SourceShapeError("A Urban não informou o endereço do imóvel")
        canonical_url = _attribute(opening.group(), "href")
        code = _attribute(opening.group(), "data-codigo")
        if not canonical_url or not code:
            raise SourceShapeError("A Urban não informou o código do imóvel")

        category = _element_text(card, "p", "category")
        location_html = _element_html(card, "p", "location") or ""
        location = _clean_text(location_html)
        neighborhood_match = re.search(r"<strong[^>]*>(.*?)</strong>", location_html, re.I | re.S)
        neighborhood = _clean_text(neighborhood_match.group(1)) if neighborhood_match else None
        price = decimal_value(_element_text(card, "p", "price"))
        image_match = re.search(r"<img\b[^>]*\bsrc=[\"']([^\"']+)", card, re.I)
        numbers = _element_html(card, "div", "numbers") or ""
        city = demand.city or "Porto Alegre"
        title = category or demand.property_type or "Imóvel"
        if neighborhood:
            title = f"{title} em {neighborhood}"
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=code,
            canonical_url=canonical_url,
            title=title,
            description=location or None,
            purpose="buy",
            property_type=(category or demand.property_type or "").split(" com ", 1)[0] or None,
            state="RS",
            city=city,
            neighborhood=neighborhood,
            address={
                "formatted": location or None,
                "neighborhood": neighborhood,
                "city": city,
                "state": "RS",
            },
            price=price,
            sale_price=price,
            bedrooms=_number(numbers, r"(\d+)\s*(?:quartos?|dormit[oó]rios?)"),
            parking_spaces=_number(numbers, r"(\d+)\s*vagas?"),
            area=_number(numbers, r"([\d.,]+)\s*m[²2]"),
            primary_image_url=html_module.unescape(image_match.group(1)) if image_match else None,
            advertiser_name="Urban Company",
            raw_data={"code": code},
            extraction_confidence=92,
        )


def _cards(value: str) -> list[str]:
    matches = list(
        re.finditer(r'<a\b(?=[^>]*class=["\'][^"\']*\bproperty-listing\b)[^>]*>', value, re.I)
    )
    if not matches:
        empty_results = re.search(
            r'<section\b[^>]*id=["\']search-results["\'][^>]*>\s*</section>',
            value,
            re.I | re.S,
        )
        zero_catalog = re.search(
            r'<meta\b[^>]*name=["\']description["\'][^>]*content=["\'][^"\']*\b0\s+'
            r'(?:casas?|apartamentos?|im[oó]veis)\b',
            value,
            re.I,
        )
        if empty_results and zero_catalog:
            return []
        raise SourceShapeError("A busca da Urban não contém imóveis reconhecíveis")
    return [
        value[
            match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(value)
        ]
        for index, match in enumerate(matches)
    ]


def _attribute(tag: str, name: str) -> str | None:
    match = re.search(rf'\b{re.escape(name)}=["\']([^"\']+)["\']', tag, re.I)
    return html_module.unescape(match.group(1)).strip() if match else None


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


def _number(value: str, pattern: str) -> int | None:
    match = re.search(pattern, _clean_text(value), re.I)
    return integer_value(match.group(1)) if match else None
