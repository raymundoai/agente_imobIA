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


class ChavesNaMaoConnector(PortalConnector):
    descriptor = SourceDescriptor("chaves_na_mao", "Chaves na Mão", "Nacional", "json_ld")
    parser_version = "chaves-jsonld-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city) is not None

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        url = _search_url(demand)
        response = self.get_public(url)
        offers = _listing_offers(response.text)
        records = [self._record(item, demand) for item in offers[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        offered = item.get("itemOffered") if isinstance(item.get("itemOffered"), dict) else {}
        address = offered.get("address") if isinstance(offered.get("address"), dict) else {}
        geo = offered.get("geo") if isinstance(offered.get("geo"), dict) else {}
        advertiser = item.get("offeredBy") if isinstance(item.get("offeredBy"), dict) else {}
        url = str(item.get("url") or offered.get("@id"))
        purpose = requested_purpose(demand) or "buy"
        price = decimal_value(item.get("price"))
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=listing_id_from_url(url),
            canonical_url=url,
            title=str(item.get("name") or "Imóvel no Chaves na Mão"),
            purpose=purpose,
            property_type=_schema_type(offered.get("@type")) or demand.property_type,
            state=(infer_state(demand.city) or "").upper() or None,
            city=demand.city or "",
            neighborhood=_text(address.get("addressLocality")),
            address={
                "street": address.get("streetAddress"),
                "neighborhood": address.get("addressLocality"),
                "city": demand.city,
                "state": infer_state(demand.city),
                "postal_code": address.get("postalCode"),
            },
            latitude=decimal_value(geo.get("latitude")),
            longitude=decimal_value(geo.get("longitude")),
            price=price,
            sale_price=price if purpose == "buy" else None,
            rent_price=price if purpose == "rent" else None,
            bedrooms=integer_value(offered.get("numberOfBedrooms") or offered.get("numberOfRooms")),
            bathrooms=integer_value(offered.get("numberOfBathroomsTotal")),
            parking_spaces=_parking_spaces(str(item.get("name") or "")),
            area=integer_value(offered.get("floorSize")),
            primary_image_url=_image(offered.get("image")),
            advertiser_name=_text(advertiser.get("name")),
            raw_data={"schema_type": offered.get("@type")},
            extraction_confidence=97,
        )


def _search_url(demand: LeadDemand) -> str:
    purpose = requested_purpose(demand)
    kind = (demand.property_type or "").casefold()
    if purpose == "rent":
        prefix = (
            "apartamentos-para-alugar"
            if "apart" in kind
            else "casas-para-alugar"
            if "casa" in kind
            else "imoveis-para-alugar"
        )
    else:
        prefix = (
            "apartamentos-a-venda"
            if "apart" in kind
            else "casas-a-venda"
            if "casa" in kind
            else "imoveis-a-venda"
        )
    state = (infer_state(demand.city) or "SP").casefold()
    return f"https://www.chavesnamao.com.br/{prefix}/{state}-{slug(demand.city)}/"


def _listing_offers(html: str) -> list[dict[str, Any]]:
    for document in json_documents(html):
        for value in walk_json(document):
            if not isinstance(value, dict) or value.get("@type") != "RealEstateListing":
                continue
            offers = value.get("offers") if isinstance(value.get("offers"), dict) else {}
            items = offers.get("itemListElement")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict) and item.get("url")]
    raise SourceShapeError("A busca do Chaves na Mão não contém ofertas estruturadas")


def _schema_type(value: object) -> str | None:
    return {
        "Apartment": "apartamento",
        "House": "casa",
        "SingleFamilyResidence": "casa",
        "Residence": "imóvel residencial",
    }.get(str(value))


def _parking_spaces(value: str) -> int | None:
    import re

    match = re.search(r"(\d+)\s+vagas?", value, re.I)
    return integer_value(match.group(1)) if match else None


def _image(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return _text(value)


def _text(value: object) -> str | None:
    return str(value).strip() if value not in (None, "") else None
