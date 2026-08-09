from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import unquote, urlencode, urlparse

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
)
from app.modules.leads.domain.entities import LeadDemand


class NovaSaoPauloConnector(PortalConnector):
    descriptor = SourceDescriptor(
        "nova_sao_paulo", "Nova São Paulo", "São Paulo", "structured_html"
    )
    parser_version = "nova-sp-cards-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city) == "SP"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        requested = requested_purpose(demand)
        params: list[tuple[str, str]] = [
            ("negotiation", "locacao" if requested == "rent" else "venda")
        ]
        if demand.price_min is not None:
            params.append(("value_min", str(int(demand.price_min))))
        if demand.price_max is not None:
            params.append(("value_max", str(int(demand.price_max))))
        if demand.min_area is not None:
            params.append(("area_min", str(demand.min_area)))
        if demand.bedrooms is not None:
            params.append(("bedrooms[]", str(demand.bedrooms)))
        if demand.parking_spaces is not None:
            params.append(("garages[]", str(demand.parking_spaces)))
        url = "https://www.novasaopaulo.com.br/imoveis?" + urlencode(params)
        response = self.get_public(url)
        blocks = re.findall(
            r'<article class="[^"]*\bcard\b[^"]*">(.*?)</article>',
            response.text,
            re.I | re.S,
        )
        if not blocks:
            raise SourceShapeError("A busca da Nova São Paulo não contém cards de imóveis")
        records = [self._record(block, demand) for block in blocks[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, block: str, demand: LeadDemand) -> ExternalListingRecord:
        share_match = re.search(r'data-share="([^"]+)"', block, re.I)
        try:
            shared = json.loads(html.unescape(share_match.group(1))) if share_match else {}
        except (json.JSONDecodeError, TypeError):
            shared = {}
        url_match = re.search(r'href="([^"]+/imovel/[^"]+)"', block, re.I)
        url = str(shared.get("url") or (url_match.group(1) if url_match else ""))
        if not url:
            raise SourceShapeError("Card da Nova São Paulo sem URL canônica")
        segments = [unquote(value) for value in urlparse(url).path.split("/") if value]
        try:
            property_index = segments.index("imovel")
        except ValueError as exc:
            raise SourceShapeError("URL de imóvel inesperada na Nova São Paulo") from exc
        path = segments[property_index + 1 :]
        property_type = path[0].replace("-", " ") if path else demand.property_type
        city = _display_slug(path[2]) if len(path) > 2 else str(demand.city or "")
        neighborhood = _class_text(block, "font-serif")
        if not neighborhood and len(path) > 3:
            neighborhood = _display_slug(path[3])
        prices = {
            label.casefold(): decimal_value(value)
            for label, value in re.findall(
                r"<label>\s*<span[^>]*>\s*(Venda|Locação)\s*</span>\s*([^<]+)</label>",
                block,
                re.I | re.S,
            )
        }
        sale_price = prices.get("venda")
        rent_price = prices.get("locação")
        requested = requested_purpose(demand)
        price = rent_price if requested == "rent" else sale_price
        purpose = available_purpose(sale_price, rent_price, requested)
        content = _plain_text(block)
        street_match = re.search(
            r'<p class="[^"]*overflow-hidden[^"]*"[^>]*>(.*?)</p>',
            block,
            re.I | re.S,
        )
        street = _plain_text(street_match.group(1)) if street_match else None
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=str(shared.get("id") or path[-1]),
            canonical_url=url,
            title=str(shared.get("title") or f"{property_type.title()} em {neighborhood}"),
            description=_limited_text(shared.get("description")),
            purpose=purpose,
            property_type=property_type,
            state="SP",
            city=str(demand.city) if demand.city else city,
            neighborhood=neighborhood,
            address={
                "street": street,
                "neighborhood": neighborhood,
                "city": str(demand.city) if demand.city else city,
                "state": "SP",
            },
            price=price,
            sale_price=sale_price,
            rent_price=rent_price,
            bedrooms=_feature(content, "quartos?"),
            parking_spaces=_feature(content, "vagas?"),
            area=_area(content),
            primary_image_url=_limited_text(shared.get("image")),
            advertiser_name="Nova São Paulo",
            raw_data={"reference": shared.get("id")},
            extraction_confidence=92,
        )


def _class_text(value: str, class_fragment: str) -> str | None:
    match = re.search(
        rf'class="[^"]*{re.escape(class_fragment)}[^"]*"[^>]*>(.*?)</[^>]+>',
        value,
        re.I | re.S,
    )
    return _plain_text(match.group(1)) if match else None


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _limited_text(value: Any, limit: int = 4_000) -> str | None:
    text = str(value).strip() if value not in (None, "") else None
    return text[:limit] if text else None


def _feature(value: str, label: str) -> int | None:
    match = re.search(rf"(\d+)\s*{label}", value, re.I)
    return integer_value(match.group(1)) if match else None


def _area(value: str) -> int | None:
    match = re.search(r"([\d.,]+)\s*m²", value, re.I)
    return integer_value(match.group(1)) if match else None


def _display_slug(value: str) -> str:
    return value.replace("-", " ").title()
