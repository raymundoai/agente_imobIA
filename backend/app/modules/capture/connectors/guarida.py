from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

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


class GuaridaConnector(PortalConnector):
    descriptor = SourceDescriptor("guarida", "Guarida Imóveis", "Rio Grande do Sul", "next_data")
    parser_version = "guarida-next-v1"

    def supports(self, demand: LeadDemand) -> bool:
        return infer_state(demand.city, demand.state) == "RS"

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        deal = "alugar" if requested_purpose(demand) == "rent" else "comprar"
        state = (infer_state(demand.city, demand.state) or "RS").casefold()
        url = (
            f"https://guarida.com.br/busca/{deal}/residencial%2Bcomercial/"
            f"{slug(demand.city)}-{state}"
        )
        response = self.get_public(url)
        items = _search_items(response.text)
        records = [self._record(item, demand, str(response.url)) for item in items[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(
        self, item: dict[str, Any], demand: LeadDemand, base_url: str
    ) -> ExternalListingRecord:
        properties = {
            str(value.get("slug")): value.get("valor")
            for value in item.get("propriedades") or []
            if isinstance(value, dict)
        }
        values = item.get("valores") if isinstance(item.get("valores"), dict) else {}
        kind = item.get("tipo") if isinstance(item.get("tipo"), dict) else {}
        photos = item.get("fotos") if isinstance(item.get("fotos"), list) else []
        photo = photos[0] if photos and isinstance(photos[0], dict) else {}
        purpose = "rent" if item.get("negocio") == "alugar" else "buy"
        price = decimal_value(values.get("valor"))
        address_text = str(item.get("endereco") or "")
        neighborhood = address_text.split(",", 1)[0].strip() or None
        city = demand.city or _city_from_address(address_text)
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=str(item.get("codigo")),
            canonical_url=urljoin(base_url, str(item.get("url") or "")),
            title=str(item.get("titulo") or f"Imóvel em {neighborhood or city}"),
            purpose=purpose,
            property_type=_text(kind.get("nome")) or demand.property_type,
            state=(infer_state(city) or "RS").upper(),
            city=city or "Porto Alegre",
            neighborhood=neighborhood,
            address={
                "street": item.get("logradouro"),
                "neighborhood": neighborhood,
                "city": city,
                "state": infer_state(city) or "RS",
            },
            latitude=decimal_value(item.get("latitude")),
            longitude=decimal_value(item.get("longitude")),
            price=price,
            sale_price=price if purpose == "buy" else None,
            rent_price=price if purpose == "rent" else None,
            condominium_fee=decimal_value(values.get("condominio")),
            property_tax=decimal_value(values.get("iptu")),
            bedrooms=integer_value(properties.get("dormitorios")),
            suites=integer_value(properties.get("suite")),
            bathrooms=integer_value(properties.get("banheiro")),
            parking_spaces=integer_value(properties.get("vaga")),
            area=integer_value(properties.get("area")),
            primary_image_url=_text(photo.get("url")),
            raw_data={"codigo": item.get("codigo"), "finalidade": item.get("finalidade")},
            extraction_confidence=96,
        )


def _search_items(html: str) -> list[dict[str, Any]]:
    for document in json_documents(html):
        try:
            items = document["props"]["pageProps"]["search"]["imoveis"]
        except (KeyError, TypeError):
            continue
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict) and item.get("codigo")]
    raise SourceShapeError("A busca da Guarida mudou de formato")


def _city_from_address(value: str) -> str | None:
    parts = [part.strip() for part in value.split(",")]
    return parts[-1].rsplit(" - ", 1)[0].strip() if len(parts) > 1 else None


def _text(value: object) -> str | None:
    return str(value).strip() if value not in (None, "") else None
