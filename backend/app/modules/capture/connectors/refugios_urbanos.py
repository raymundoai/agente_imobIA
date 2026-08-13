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
    listing_id_from_url,
    requested_purpose,
    slug,
)
from app.modules.leads.domain.entities import LeadDemand


class RefugiosUrbanosConnector(PortalConnector):
    descriptor = SourceDescriptor(
        "refugios_urbanos", "Refúgios Urbanos", "São Paulo", "structured_html"
    )
    parser_version = "refugios-cards-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return (
            infer_state(demand.city, demand.state) == "SP"
            and requested_purpose(demand) != "rent"
        )

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        if demand.neighborhoods:
            url = f"https://refugiosurbanos.com.br/bairros_imovel/{slug(demand.neighborhoods[0])}/"
        else:
            url = "https://refugiosurbanos.com.br/imoveis/"
        response = self.get_public(url)
        items = _cards(response.text)
        records = [self._record(item, demand) for item in items[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        title = str(item["title"])
        composition = str(item.get("composition") or "")
        price = decimal_value(item.get("price"))
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=str(item.get("code") or listing_id_from_url(str(item["url"]))),
            canonical_url=str(item["url"]),
            title=title,
            purpose="buy",
            property_type=_property_type(title) or demand.property_type,
            state="SP",
            city=demand.city or "São Paulo",
            neighborhood=_text(item.get("neighborhood")),
            address={
                "neighborhood": item.get("neighborhood"),
                "city": demand.city or "São Paulo",
                "state": "SP",
            },
            price=price,
            sale_price=price,
            bedrooms=_number(composition, r"(\d+)\s+quartos?"),
            suites=_number(composition, r"(\d+)\s+su[ií]tes?"),
            bathrooms=_number(composition, r"(\d+)\s+banheiros?"),
            parking_spaces=(
                0
                if re.search(r"sem\s+vaga", composition, re.I)
                else _number(composition, r"(\d+)\s+vagas?")
            ),
            area=_number(composition, r"([\d.,]+)\s*m\s*[²2]"),
            primary_image_url=_text(item.get("image")),
            advertiser_name="Refúgios Urbanos",
            raw_data={"code": item.get("code")},
            extraction_confidence=86,
        )


def _cards(html: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r'<article\b[^>]*class=["\'][^"\']*\bimovel\b[^"\']*["\'][^>]*>(.*?)</article>',
        html,
        re.I | re.S,
    ):
        block = match.group(1)
        anchors = re.findall(
            r'<a\b[^>]*href=["\']([^"\']*/imoveis/[^"\']+)["\'][^>]*>(.*?)</a>',
            block,
            re.I | re.S,
        )
        url = next((href for href, _ in anchors if "?" not in href), None)
        titles = [_plain_text(body) for _, body in anchors]
        title = max((value for value in titles if value), key=len, default="")
        if not url or not title or url in seen:
            continue
        seen.add(url)
        price = _class_text(block, "preco-imovel")
        composition = _class_text(block, "composicao")
        identity = re.search(r"RU:\s*(\d+)\s*-\s*([^<]+)", block, re.I)
        image = _attribute(block, "data-lazy-src") or _attribute(block, "src")
        if image and image.startswith("data:image"):
            image = None
        results.append(
            {
                "url": html_module.unescape(url),
                "title": title,
                "price": price,
                "composition": composition,
                "code": identity.group(1) if identity else None,
                "neighborhood": _plain_text(identity.group(2)) if identity else None,
                "image": html_module.unescape(image) if image else None,
            }
        )
    if not results:
        raise SourceShapeError("A busca do Refúgios Urbanos não contém cards reconhecíveis")
    return results


def _class_text(block: str, class_name: str) -> str | None:
    match = re.search(
        rf'<(?P<tag>[a-z0-9]+)[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b'
        rf'[^"\']*["\'][^>]*>(?P<body>.*?)</(?P=tag)>',
        block,
        re.I | re.S,
    )
    return _plain_text(match.group("body")) if match else None


def _attribute(block: str, name: str) -> str | None:
    match = re.search(rf'\b{re.escape(name)}=["\']([^"\']+)["\']', block, re.I)
    return match.group(1) if match else None


def _plain_text(value: str) -> str:
    return " ".join(html_module.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _number(value: str, pattern: str) -> int | None:
    match = re.search(pattern, value, re.I)
    return integer_value(match.group(1)) if match else None


def _property_type(title: str) -> str | None:
    normalized = title.casefold()
    for needle, kind in (
        ("cobertura", "cobertura"),
        ("garden", "apartamento garden"),
        ("apartamento", "apartamento"),
        ("apto", "apartamento"),
        ("casa", "casa"),
        ("studio", "studio"),
    ):
        if needle in normalized:
            return kind
    return None


def _text(value: object) -> str | None:
    return str(value).strip() if value not in (None, "") else None
