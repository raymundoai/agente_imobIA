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


class QuintoAndarConnector(PortalConnector):
    descriptor = SourceDescriptor("quintoandar", "QuintoAndar", "Nacional", "json_ld")
    parser_version = "quintoandar-jsonld-v1"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        state = (infer_state(demand.city, demand.state) or "SP").casefold()
        action = "alugar" if requested_purpose(demand) == "rent" else "comprar"
        kind = slug(demand.property_type) or "imovel"
        url = (
            f"https://www.quintoandar.com.br/{action}/imovel/"
            f"{slug(demand.city)}-{state}-brasil/{kind}"
        )
        response = self.get_public(url)
        candidates = []
        for document in json_documents(response.text):
            for value in walk_json(document):
                if isinstance(value, dict) and value.get("@type") == "RealEstateListing":
                    candidates.append(value)
        if not candidates:
            raise SourceShapeError("A busca do QuintoAndar não contém imóveis estruturados")
        records = [self._record(item, demand) for item in candidates[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        about = item.get("about") if isinstance(item.get("about"), dict) else {}
        address = about.get("address") if isinstance(about.get("address"), dict) else {}
        offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
        url = str(item.get("url") or item.get("@id"))
        purpose = requested_purpose(demand)
        price = decimal_value(offers.get("price"))
        street = str(address.get("streetAddress") or "")
        neighborhood = street.rsplit(",", 1)[1].strip() if "," in street else None
        image = item.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        property_type = _schema_type(about.get("@type")) or demand.property_type
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=listing_id_from_url(url),
            canonical_url=url,
            title=str(item.get("name") or about.get("name") or "Imóvel no QuintoAndar"),
            description=_text(item.get("description")),
            purpose=purpose,
            property_type=property_type,
            state=str(
                address.get("addressRegion")
                or infer_state(demand.city, demand.state)
                or ""
            ).upper()
            or None,
            city=str(address.get("addressLocality") or demand.city or ""),
            neighborhood=neighborhood,
            address={
                "street": street or None,
                "neighborhood": neighborhood,
                "city": address.get("addressLocality") or demand.city,
                "state": address.get("addressRegion")
                or infer_state(demand.city, demand.state),
            },
            price=price,
            sale_price=price if purpose == "buy" else None,
            rent_price=price if purpose == "rent" else None,
            bedrooms=integer_value(about.get("numberOfBedrooms") or about.get("numberOfRooms")),
            bathrooms=integer_value(about.get("numberOfFullBathrooms")),
            area=integer_value(about.get("floorSize")),
            primary_image_url=_text(image),
            raw_data={"schema_type": about.get("@type")},
            extraction_confidence=96,
        )


def _schema_type(value: Any) -> str | None:
    return {
        "Apartment": "apartamento",
        "House": "casa",
        "SingleFamilyResidence": "casa",
    }.get(str(value))


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
