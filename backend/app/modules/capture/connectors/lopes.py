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
from app.modules.leads.domain.entities import LeadDemand


class LopesConnector(PortalConnector):
    descriptor = SourceDescriptor("lopes", "Lopes", "Nacional", "json")
    parser_version = "lopes-json-v1"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        state = (infer_state(demand.city) or "SP").casefold()
        deal = "rent" if requested_purpose(demand) == "rent" else "sale"
        url = (
            "https://apis.lopes.com.br/portal-home/v2/search/cache/"
            f"{deal}/br/{state}/{slug(demand.city)}"
        )
        response = self.get_public(url)
        try:
            payload = response.json()
            products = payload["products"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceShapeError("A resposta da Lopes mudou de formato") from exc
        if not isinstance(products, list):
            raise SourceShapeError("A resposta da Lopes não contém uma lista de imóveis")
        records = [self._record(item, demand) for item in products[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        attributes = {
            str(attribute.get("type") or attribute.get("name")): attribute.get("value")
            for attribute in item.get("attributes") or []
            if isinstance(attribute, dict)
        }
        location = item.get("locationDTO") or {}
        listing_id = str(item.get("id") or item.get("sku"))
        photos = item.get("photo") or []
        photo = photos[0] if photos and isinstance(photos[0], dict) else {}
        price = decimal_value(item.get("sellingPriceFormat") or item.get("priceFormat"))
        purpose = "rent" if item.get("dealType") == "rent" else "buy"
        property_type = str(item.get("type") or demand.property_type or "Imóvel")
        bedrooms = integer_value(attributes.get("bedroom_attr"))
        city = str(location.get("city") or demand.city or "")
        neighborhood = str(location.get("neighborhood") or "").strip() or None
        title_parts = [property_type]
        if bedrooms is not None:
            title_parts.append(f"com {bedrooms} quartos")
        if neighborhood:
            title_parts.append(f"em {neighborhood}")
        canonical_url = f"https://www.lopes.com.br/imovel/{listing_id}"
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=listing_id,
            canonical_url=canonical_url,
            title=" ".join(title_parts),
            description=_text(item.get("description")),
            purpose=purpose,
            property_type=property_type,
            state=str(location.get("uf") or infer_state(city) or "").upper() or None,
            city=city,
            neighborhood=neighborhood,
            address={
                "street": location.get("address") or item.get("street"),
                "number": location.get("number"),
                "neighborhood": neighborhood,
                "city": city,
                "state": str(location.get("uf") or infer_state(city) or "").upper() or None,
            },
            latitude=decimal_value(item.get("lat")),
            longitude=decimal_value(item.get("lng")),
            price=price,
            sale_price=price if purpose == "buy" else None,
            rent_price=price if purpose == "rent" else None,
            bedrooms=bedrooms,
            bathrooms=integer_value(attributes.get("bathroom_attr")),
            parking_spaces=integer_value(attributes.get("parking_lots_attr")),
            area=integer_value(attributes.get("area_attr")),
            primary_image_url=_text(
                photo.get("mediumUrl") or photo.get("largeUrl") or photo.get("smallUrl")
            ),
            advertiser_name=_text((item.get("company") or {}).get("name")),
            raw_data={"id": listing_id, "dealType": item.get("dealType")},
            extraction_confidence=95,
        )


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
