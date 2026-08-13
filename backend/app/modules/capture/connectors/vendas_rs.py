from __future__ import annotations

import html as html_module
import re
from urllib.parse import urlencode, urljoin

from app.modules.capture.connectors.base import (
    ConnectorBatch,
    ExternalListingRecord,
    PortalConnector,
    SourceDescriptor,
    SourceShapeError,
    decimal_value,
    infer_state,
    listing_id_from_url,
    requested_purpose,
)
from app.modules.leads.domain.entities import LeadDemand


class VendasRSConnector(PortalConnector):
    descriptor = SourceDescriptor(
        "vendas_rs",
        "Vendas de Imóveis RS",
        "Rio Grande do Sul",
        "json_api",
    )
    parser_version = "vendas-rs-api-v1"
    origin = "https://vendasimoveis.rs.gov.br"
    endpoint = f"{origin}/_service/conteudo/pagedlistfilho"

    def supports(self, demand: LeadDemand) -> bool:
        return (
            infer_state(demand.city, demand.state) == "RS"
            and requested_purpose(demand) != "rent"
        )

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        params = [
            ("id", "98"),
            ("templatename", "pagina.listapagina.imoveis"),
            ("currentPage", "1"),
            ("pageSize", str(limit)),
            ("filterData", ""),
            ("fields[]", "Titulo"),
            ("fields[]", "TituloCurto"),
            ("fields[]", "Texto"),
            ("form[municipio]", demand.city or ""),
            ("form[ordem]", "RECENTES"),
        ]
        url = f"{self.endpoint}?{urlencode(params)}"
        response = self.get_public(url, headers={"Accept": "application/json"})
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceShapeError(
                "O portal Vendas de Imóveis RS retornou dados inválidos"
            ) from exc
        body = payload.get("body") if isinstance(payload, dict) else None
        if not isinstance(body, str):
            raise SourceShapeError("O portal Vendas de Imóveis RS mudou de formato")
        records = [self._record(card, demand) for card in _cards(body)[:limit]]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records)

    def _record(self, card: str, demand: LeadDemand) -> ExternalListingRecord:
        href_match = re.search(r'<a\b[^>]*href=["\']([^"\']+)', card, re.I)
        if not href_match:
            raise SourceShapeError("O portal Vendas de Imóveis RS não informou a URL")
        canonical_url = urljoin(self.origin, html_module.unescape(href_match.group(1)))
        title = _element_text(card, "h3", "artigo__listapaginas__item__titulo")
        property_type = _element_text(card, "a", "label-warning") or demand.property_type
        location = _element_text(card, "p", "artigo__listapaginas__item__descricao")
        prices = [
            decimal_value(_clean_text(value))
            for value in re.findall(
                r'<p\b[^>]*class=["\'][^"\']*artigo__listapaginas__item__valor[^"\']*["\'][^>]*>(.*?)</p>',
                card,
                re.I | re.S,
            )
        ]
        prices = [price for price in prices if price is not None]
        price = min(prices) if prices else None
        image_match = re.search(r'<img\b[^>]*src=["\']([^"\']+)', card, re.I)
        city = demand.city or _city(location) or "Porto Alegre"
        neighborhood = _neighborhood(title, city)
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=listing_id_from_url(canonical_url),
            canonical_url=canonical_url,
            title=title or f"Imóvel em {city}",
            description=location,
            purpose="buy",
            property_type=property_type,
            state="RS",
            city=city,
            neighborhood=neighborhood,
            address={
                "formatted": location,
                "neighborhood": neighborhood,
                "city": city,
                "state": "RS",
            },
            price=price,
            sale_price=price,
            primary_image_url=(
                urljoin(self.origin, html_module.unescape(image_match.group(1)))
                if image_match
                else None
            ),
            advertiser_name="Governo do Estado do Rio Grande do Sul",
            raw_data={"public_portal": True},
            extraction_confidence=88,
        )


def _cards(value: str) -> list[str]:
    matches = list(
        re.finditer(
            r'<div\b(?=[^>]*class=["\'][^"\']*\bartigo__listapaginas__item\b)[^>]*>',
            value,
            re.I,
        )
    )
    return [
        value[
            match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(value)
        ]
        for index, match in enumerate(matches)
    ]


def _element_text(value: str, tag: str, class_name: str) -> str | None:
    match = re.search(
        rf'<{tag}\b[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>(.*?)</{tag}>',
        value,
        re.I | re.S,
    )
    return _clean_text(match.group(1)) if match else None


def _clean_text(value: str) -> str:
    return " ".join(html_module.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _city(value: str | None) -> str | None:
    match = re.search(r"([^,-]+)\s*-\s*RS", value or "", re.I)
    return match.group(1).strip() if match else None


def _neighborhood(title: str | None, city: str) -> str | None:
    match = re.search(rf"-\s*(.*?),\s*{re.escape(city)}\b", title or "", re.I)
    return match.group(1).strip() if match else None
