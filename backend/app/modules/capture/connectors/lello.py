from __future__ import annotations

from app.modules.capture.connectors.base import (
    ConnectorBatch,
    ExternalListingRecord,
    PortalConnector,
    SourceDescriptor,
    decimal_value,
    infer_state,
    integer_value,
    listing_id_from_url,
    requested_purpose,
)
from app.modules.capture.connectors.html import json_documents, walk_json
from app.modules.capture.discovery import parse_public_listing_html
from app.modules.capture.portals import build_portal_searches
from app.modules.leads.domain.entities import LeadDemand


class LelloConnector(PortalConnector):
    descriptor = SourceDescriptor("lello", "Lello Imóveis", "São Paulo", "json_ld")
    parser_version = "lello-public-v2"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city) == "SP"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        url = next(item.url for item in build_portal_searches(demand) if item.id == "lello")
        response = self.get_public(url)
        discovered = parse_public_listing_html(
            self.descriptor.id, str(response.url), response.text, limit=limit
        )
        native_by_id = _native_items_by_id(response.text)
        records = []
        for item in discovered:
            purpose = requested_purpose(demand)
            price = decimal_value(item.price)
            neighborhood = item.neighborhood
            city = item.city
            # Some Lello JSON-LD payloads expose the neighborhood in addressLocality and
            # the state in addressRegion. The demand remains the authoritative city filter.
            if city.casefold() != (demand.city or "").casefold() and item.neighborhood == "SP":
                neighborhood = city
                city = demand.city or city
            listing_id = listing_id_from_url(item.source_url)
            native = native_by_id.get(listing_id, {})
            photos = native.get("fotos") if isinstance(native.get("fotos"), list) else []
            primary_photo = next(
                (
                    photo
                    for photo in photos
                    if isinstance(photo, dict) and photo.get("fotoPrincipal")
                ),
                photos[0] if photos and isinstance(photos[0], dict) else {},
            )
            price = decimal_value(
                native.get("valorVenda")
                or native.get("valorCampanhaVenda")
                or native.get("valorVendaMin")
                or item.price
            )
            records.append(
                ExternalListingRecord(
                    source_id=self.descriptor.id,
                    source_listing_id=listing_id,
                    canonical_url=item.source_url,
                    title=(
                        item.title
                        if item.title.casefold() not in {"apartment", "house", "product"}
                        else f"{demand.property_type or 'Imóvel'} em {neighborhood or city}"
                    ),
                    purpose=purpose,
                    property_type=(
                        str(native.get("subTipoImovel") or native.get("tipoImovel") or "").strip()
                        or item.property_type
                        or demand.property_type
                    ),
                    state="SP",
                    city=city,
                    neighborhood=neighborhood,
                    address={
                        "street": native.get("endereco"),
                        "neighborhood": neighborhood,
                        "city": city,
                        "state": native.get("uf") or "SP",
                    },
                    latitude=decimal_value(native.get("latitude")),
                    longitude=decimal_value(native.get("longitude")),
                    price=price,
                    sale_price=price if purpose == "buy" else None,
                    rent_price=price if purpose == "rent" else None,
                    condominium_fee=decimal_value(native.get("previsaoCondominio")),
                    property_tax=decimal_value(native.get("previsaoIptu")),
                    bedrooms=integer_value(native.get("quantidadeDormitorios")) or item.bedrooms,
                    suites=integer_value(native.get("quantidadeSuites")),
                    bathrooms=integer_value(native.get("quantidadeBanheiros")) or item.bathrooms,
                    parking_spaces=integer_value(native.get("quantidadeVagas"))
                    or item.parking_spaces,
                    area=integer_value(native.get("metragemPrincipal")) or item.area,
                    primary_image_url=_text(
                        primary_photo.get("enderecoFoto")
                        or native.get("enderecoFotoPrincipal")
                        or native.get("enderecoFotoPrincipalEmpreendimento")
                    ),
                    advertiser_name=_text(native.get("descricaoFilial")),
                    advertiser_phone=_text(native.get("telefoneFilial")),
                    raw_data={"idImovel": native.get("idImovel") or listing_id},
                    extraction_confidence=94 if native else 82,
                )
            )
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)


def _native_items_by_id(html: str) -> dict[str, dict]:
    items: dict[str, dict] = {}
    for document in json_documents(html):
        for value in walk_json(document):
            if not isinstance(value, dict) or value.get("idImovel") in (None, ""):
                continue
            items[str(value["idImovel"])] = value
    return items


def _text(value: object) -> str | None:
    return str(value).strip() if value not in (None, "") else None
