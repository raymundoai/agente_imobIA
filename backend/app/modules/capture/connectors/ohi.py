from __future__ import annotations

import html
import re
from urllib.parse import unquote, urlencode, urljoin, urlparse

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
    listing_id_from_url,
    requested_purpose,
)
from app.modules.leads.domain.entities import LeadDemand


class OhiConnector(PortalConnector):
    descriptor = SourceDescriptor("ohi", "OHI Imóveis", "São Paulo", "structured_html")
    parser_version = "ohi-cards-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city) == "SP"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        requested = requested_purpose(demand)
        query = demand.neighborhoods[0] if demand.neighborhoods else demand.city
        url = "https://www.ohimoveis.com.br/busca?" + urlencode(
            {"mode": "rent" if requested == "rent" else "sale", "q": query or ""}
        )
        response = self.get_public(url)
        blocks = re.findall(r'(<a class="ohi-card".*?</a>)', response.text, re.I | re.S)
        if not blocks:
            raise SourceShapeError("A busca da OHI não contém cards de imóveis")
        records = [self._record(block, demand) for block in blocks[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, block: str, demand: LeadDemand) -> ExternalListingRecord:
        href = _tag_attribute(block, "ohi-card", "href")
        if not href:
            raise SourceShapeError("Card da OHI sem URL canônica")
        url = urljoin("https://www.ohimoveis.com.br", href)
        segments = [unquote(value) for value in urlparse(url).path.split("/") if value]
        path = segments[segments.index("imovel") + 1 :] if "imovel" in segments else []
        city = _display_slug(path[0]) if path else str(demand.city or "")
        neighborhood = _class_text(block, "ohi-card__neigh")
        if not neighborhood and len(path) > 1:
            neighborhood = _display_slug(path[1])
        property_type = _display_slug(path[3]) if len(path) > 3 else demand.property_type
        requested = requested_purpose(demand)
        main_price = decimal_value(_class_text(block, "ohi-card__price"))
        alternate_label = (_class_text(block, "ohi-card__price-alt-label") or "").casefold()
        alternate_price = decimal_value(_class_text(block, "ohi-card__price-alt-val"))
        sale_price = main_price if requested == "buy" else None
        rent_price = main_price if requested == "rent" else None
        if "venda" in alternate_label:
            sale_price = alternate_price
        elif "aluguel" in alternate_label:
            rent_price = alternate_price
        purpose = available_purpose(sale_price, rent_price, requested)
        facts = _class_texts(block, "ohi-card__fact")
        costs = _class_text(block, "ohi-card__costs") or ""
        address = _tag_attribute(block, "ohi-card", "aria-label")
        image = _tag_attribute(block, "ohi-card__img", "src")
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=(
                _class_text(block, "ohi-card__code") or listing_id_from_url(url)
            ).upper(),
            canonical_url=url,
            title=f"{property_type or 'Imóvel'} em {neighborhood or city}",
            purpose=purpose,
            property_type=property_type,
            state="SP",
            city=str(demand.city) if demand.city and city.casefold() == "sao paulo" else city,
            neighborhood=neighborhood,
            address={
                "street": address,
                "neighborhood": neighborhood,
                "city": city,
                "state": "SP",
            },
            price=rent_price if requested == "rent" else sale_price,
            sale_price=sale_price,
            rent_price=rent_price,
            condominium_fee=_labeled_price(costs, r"Cond\.?"),
            property_tax=_labeled_price(costs, "IPTU"),
            bedrooms=_fact(facts, 1),
            bathrooms=_fact(facts, 2),
            parking_spaces=_fact(facts, 3),
            area=_area(facts[0] if facts else ""),
            primary_image_url=image,
            advertiser_name="OHI Imóveis",
            raw_data={"mode": requested},
            extraction_confidence=93,
        )


def _tag_attribute(value: str, class_name: str, attribute: str) -> str | None:
    for match in re.finditer(r"<(?P<tag>[a-z0-9]+)(?P<attrs>[^>]*)>", value, re.I):
        classes = re.search(r'class="([^"]*)"', match.group("attrs"), re.I)
        if not classes or class_name not in classes.group(1).split():
            continue
        found = re.search(rf'{re.escape(attribute)}="([^"]*)"', match.group("attrs"), re.I)
        return html.unescape(found.group(1)) if found else None
    return None


def _class_texts(value: str, class_name: str) -> list[str]:
    found = []
    for match in re.finditer(r"<(?P<tag>[a-z0-9]+)(?P<attrs>[^>]*)>", value, re.I):
        classes = re.search(r'class="([^"]*)"', match.group("attrs"), re.I)
        if not classes or class_name not in classes.group(1).split():
            continue
        end = value.find(f"</{match.group('tag')}>", match.end())
        if end < 0:
            continue
        text = _plain_text(value[match.end() : end])
        if text:
            found.append(text)
    return found


def _class_text(value: str, class_name: str) -> str | None:
    values = _class_texts(value, class_name)
    return values[0] if values else None


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _labeled_price(value: str, label: str):
    match = re.search(rf"{label}\s*R\$\s*([\d.,]+)", value, re.I)
    return decimal_value(match.group(1)) if match else None


def _fact(values: list[str], index: int) -> int | None:
    return integer_value(values[index]) if len(values) > index else None


def _area(value: str) -> int | None:
    match = re.search(r"([\d.,]+)\s*m²", value, re.I)
    return integer_value(match.group(1)) if match else None


def _display_slug(value: str) -> str:
    return value.replace("-", " ").title()
