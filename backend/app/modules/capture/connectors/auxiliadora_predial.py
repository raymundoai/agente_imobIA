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
    listing_id_from_url,
    requested_purpose,
    slug,
)
from app.modules.capture.connectors.html import json_documents, walk_json
from app.modules.leads.domain.entities import LeadDemand


class AuxiliadoraPredialConnector(PortalConnector):
    descriptor = SourceDescriptor(
        "auxiliadora_predial",
        "Auxiliadora Predial",
        "São Paulo e Rio Grande do Sul",
        "json_ld",
    )
    parser_version = "auxiliadora-jsonld-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city, demand.state) in {"SP", "RS"}

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        purpose = requested_purpose(demand)
        action = "alugar" if purpose == "rent" else "comprar"
        state = (infer_state(demand.city, demand.state) or "RS").casefold()
        url = (
            f"https://www.auxiliadorapredial.com.br/{action}/residencial/"
            f"{state}+{slug(demand.city)}"
        )
        response = self.get_public(url)
        candidates = []
        for document in json_documents(response.text):
            for value in walk_json(document):
                if isinstance(value, dict) and value.get("@type") == "RealEstateListing":
                    url = str(value.get("url") or value.get("@id") or "")
                    if value.get("identifier") and url and not url.endswith("/null"):
                        candidates.append(value)
        if not candidates:
            raise SourceShapeError("A busca da Auxiliadora Predial não contém imóveis estruturados")
        records = [self._record(item, demand) for item in candidates[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        offers = item.get("offers")
        if isinstance(offers, list):
            offer = next((value for value in offers if isinstance(value, dict)), {})
        else:
            offer = offers if isinstance(offers, dict) else {}
        offered = offer.get("itemOffered")
        offered = offered if isinstance(offered, dict) else {}
        address = offered.get("address")
        address = address if isinstance(address, dict) else {}
        geo = offered.get("geo")
        geo = geo if isinstance(geo, dict) else {}
        purpose = requested_purpose(demand)
        price = decimal_value(offer.get("price"))
        city = str(address.get("addressLocality") or demand.city or "")
        url = str(item.get("url") or item.get("@id"))
        image = item.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("contentUrl") or image.get("url")
        amenities = offered.get("amenityFeature")
        amenities = amenities if isinstance(amenities, list) else []
        parking = next(
            (
                integer_value(value.get("value"))
                for value in amenities
                if isinstance(value, dict) and "vaga" in str(value.get("name") or "").casefold()
            ),
            None,
        )
        title = str(item.get("name") or "Imóvel na Auxiliadora Predial")
        neighborhood = _neighborhood(title, city)
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=str(item.get("identifier") or listing_id_from_url(url)),
            canonical_url=url,
            title=title,
            description=_text(item.get("description")),
            purpose=purpose,
            property_type=_text(offered.get("accommodationCategory")) or demand.property_type,
            state=infer_state(city) or infer_state(demand.city, demand.state),
            city=city,
            neighborhood=neighborhood,
            address={
                "street": address.get("streetAddress"),
                "neighborhood": neighborhood,
                "city": city,
                "state": infer_state(city) or infer_state(demand.city, demand.state),
            },
            latitude=decimal_value(geo.get("latitude")),
            longitude=decimal_value(geo.get("longitude")),
            price=price,
            sale_price=price if purpose == "buy" else None,
            rent_price=price if purpose == "rent" else None,
            bedrooms=integer_value(offered.get("numberOfBedrooms")),
            bathrooms=integer_value(offered.get("numberOfBathroomsTotal")),
            parking_spaces=parking,
            area=integer_value(offered.get("floorSize")),
            primary_image_url=_text(image),
            advertiser_name="Auxiliadora Predial",
            raw_data={"schema_type": offered.get("@type")},
            extraction_confidence=97,
        )


def _neighborhood(title: str, city: str) -> str | None:
    parts = [part.strip() for part in title.split(" - ") if part.strip()]
    if len(parts) >= 3 and parts[-1].casefold() == city.casefold():
        return parts[-2]
    return None


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
