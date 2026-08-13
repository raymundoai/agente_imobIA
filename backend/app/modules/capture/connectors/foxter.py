from __future__ import annotations

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
from app.modules.capture.connectors.html import json_documents
from app.modules.leads.domain.entities import LeadDemand


class FoxterConnector(PortalConnector):
    descriptor = SourceDescriptor("foxter", "Foxter", "Rio Grande do Sul", "next_data")
    parser_version = "foxter-next-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return (
            infer_state(demand.city, demand.state) == "RS"
            and requested_purpose(demand) != "rent"
        )

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        state = (infer_state(demand.city, demand.state) or "RS").casefold()
        url = (
            "https://www.foxterciaimobiliaria.com.br/imoveis/a-venda/"
            f"em-{slug(demand.city)}-{state}"
        )
        response = self.get_public(url)
        items = _results(response.text)
        records = [self._record(item, demand) for item in items[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        code = str(item.get("code"))
        images = item.get("images") if isinstance(item.get("images"), dict) else {}
        image_items = images.get("data") if isinstance(images.get("data"), list) else []
        image = image_items[0] if image_items and isinstance(image_items[0], dict) else {}
        etag = _text(image.get("etag"))
        city = _text(item.get("city")) or demand.city or "Porto Alegre"
        state = _text(item.get("state")) or infer_state(city) or "RS"
        price = decimal_value(item.get("price"))
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=code,
            canonical_url=f"https://www.foxterciaimobiliaria.com.br/imovel/{code}",
            title=str(item.get("title") or f"Imóvel em {item.get('district') or city}").strip(),
            purpose="buy",
            property_type=_text(item.get("type")) or demand.property_type,
            state=state.upper(),
            city=city,
            neighborhood=_text(item.get("district")),
            address={
                "street": item.get("place"),
                "neighborhood": item.get("district"),
                "city": city,
                "state": state,
            },
            price=price,
            sale_price=price,
            condominium_fee=decimal_value(item.get("condominiumAmountValue")),
            bedrooms=integer_value(item.get("bedrooms")),
            bathrooms=integer_value(item.get("bathrooms")),
            parking_spaces=integer_value(item.get("parkingSpaces")),
            area=integer_value(item.get("areaPrivate") or item.get("areaTotal")),
            primary_image_url=(
                f"https://images.foxter.com.br/rest/image/outer/480/1/foxter/wm/{etag}"
                if etag
                else None
            ),
            advertiser_name="Foxter Cia Imobiliária",
            raw_data={"code": item.get("code"), "isMarketplace": item.get("isMarketplace")},
            extraction_confidence=96,
        )


def _results(html: str) -> list[dict[str, Any]]:
    for document in json_documents(html):
        try:
            items = document["props"]["pageProps"]["results"]
        except (KeyError, TypeError):
            continue
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict) and item.get("code")]
    raise SourceShapeError("A busca da Foxter mudou de formato")


def _text(value: object) -> str | None:
    return str(value).strip() if value not in (None, "") else None
