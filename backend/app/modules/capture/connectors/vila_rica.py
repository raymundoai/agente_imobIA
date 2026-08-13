from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

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


class VilaRicaConnector(PortalConnector):
    descriptor = SourceDescriptor(
        "vila_rica",
        "Vila Rica Imóveis",
        "Rio Grande do Sul",
        "json_api",
    )
    parser_version = "vila-rica-vista-v1"
    endpoint = "https://vilarica-rest.vistahost.com.br/imoveis/listar"
    # Chave publicada pelo próprio site para consulta anônima ao catálogo Vista.
    public_catalog_key = "e8e784a96daf40964790992985f96078"
    fields = (
        "Codigo",
        "Cidade",
        "Bairro",
        "BairroComercial",
        "ValorVenda",
        "ValorLocacao",
        "Dormitorios",
        "Suites",
        "BanheiroSocialQtd",
        "Vagas",
        "AreaTotal",
        "AreaPrivativa",
        "TipoImovel",
        "FotoDestaque",
        "Categoria",
        "Finalidade",
        "Status",
        "TituloSite",
        "Endereco",
        "Latitude",
        "Longitude",
    )

    def supports(self, demand: LeadDemand) -> bool:
        return (
            infer_state(demand.city, demand.state) == "RS"
            and requested_purpose(demand) != "rent"
        )

    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        params: list[tuple[str, str]] = [
            ("key", self.public_catalog_key),
            ("pesquisa[paginacao][pagina]", "1"),
            ("pesquisa[paginacao][quantidade]", str(limit)),
            ("pesquisa[filter][Cidade]", demand.city or ""),
        ]
        if demand.property_type:
            params.append(("pesquisa[filter][Categoria]", demand.property_type))
        if demand.bedrooms:
            params.append(("pesquisa[filter][Dormitorios]", str(demand.bedrooms)))
        if demand.parking_spaces:
            params.append(("pesquisa[filter][Vagas]", str(demand.parking_spaces)))
        params.extend(
            (f"pesquisa[fields][{index}]", field) for index, field in enumerate(self.fields)
        )
        url = f"{self.endpoint}?{urlencode(params)}"
        response = self.get_public(url, headers={"Accept": "application/json"})
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceShapeError("A consulta da Vila Rica retornou dados inválidos") from exc
        if isinstance(payload, dict) and payload.get("message"):
            return ConnectorBatch(self.descriptor, self.parser_version, url, [])
        if not isinstance(payload, dict):
            raise SourceShapeError("A consulta da Vila Rica mudou de formato")
        records = [
            self._record(item, demand)
            for item in payload.values()
            if isinstance(item, dict) and item.get("Codigo")
        ]
        return ConnectorBatch(self.descriptor, self.parser_version, url, records[:limit])

    def _record(self, item: dict[str, Any], demand: LeadDemand) -> ExternalListingRecord:
        code = str(item["Codigo"])
        city = _text(item.get("Cidade")) or demand.city or "Porto Alegre"
        neighborhood = _text(item.get("BairroComercial")) or _text(item.get("Bairro"))
        property_type = _text(item.get("Categoria")) or demand.property_type
        sale_price = _positive_decimal(item.get("ValorVenda"))
        search_url = (
            f"https://www.vilarica.com.br/comprar/residencial/{slug(city)}-rs#codigo={code}"
        )
        title = _text(item.get("TituloSite"))
        if not title:
            title = f"{property_type or 'Imóvel'} em {neighborhood or city}"
        street = _text(item.get("Endereco"))
        return ExternalListingRecord(
            source_id=self.descriptor.id,
            source_listing_id=code,
            canonical_url=search_url,
            title=title,
            purpose="buy",
            property_type=property_type,
            state="RS",
            city=city,
            neighborhood=neighborhood,
            address={
                "street": street,
                "neighborhood": neighborhood,
                "city": city,
                "state": "RS",
            },
            latitude=decimal_value(item.get("Latitude")),
            longitude=decimal_value(item.get("Longitude")),
            price=sale_price,
            sale_price=sale_price,
            bedrooms=integer_value(item.get("Dormitorios")),
            suites=integer_value(item.get("Suites")),
            bathrooms=integer_value(item.get("BanheiroSocialQtd")),
            parking_spaces=integer_value(item.get("Vagas")),
            area=integer_value(item.get("AreaPrivativa")) or integer_value(item.get("AreaTotal")),
            primary_image_url=_text(item.get("FotoDestaque")),
            advertiser_name="Vila Rica Imóveis",
            raw_data={"code": code, "status": item.get("Status")},
            extraction_confidence=94,
        )


def _positive_decimal(value: Any):
    parsed = decimal_value(value)
    return parsed if parsed is not None and parsed > 0 else None


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None
