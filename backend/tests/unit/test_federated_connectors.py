from decimal import Decimal
from uuid import uuid4

import httpx

from app.modules.capture.connectors.lello import LelloConnector
from app.modules.capture.connectors.lopes import LopesConnector
from app.modules.capture.connectors.quintoandar import QuintoAndarConnector
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose


def _demand() -> LeadDemand:
    return LeadDemand(
        tenant_id=uuid4(),
        lead_name="Bruna",
        phone="5551999999999",
        purpose=LeadPurpose.BUY,
        property_type="apartamento",
        city="São Paulo",
        neighborhoods=["Pinheiros"],
        price_max=Decimal("1500000"),
        bedrooms=2,
    )


def test_lopes_connector_normalizes_public_json() -> None:
    payload = {
        "products": {
            "content": [
                {
                    "id": "REO123456",
                    "type": "Apartamento",
                    "priceFormat": "R$ 1.250.000",
                    "sellingPriceFormat": "R$ 1.250.000",
                    "dealType": "sale",
                    "description": "Apartamento iluminado",
                    "attributes": [
                        {"type": "area_attr", "value": "88m²"},
                        {"type": "bedroom_attr", "value": "3"},
                        {"type": "bathroom_attr", "value": "2"},
                        {"type": "parking_lots_attr", "value": "1"},
                    ],
                    "locationDTO": {
                        "address": "Rua dos Pinheiros",
                        "city": "São Paulo",
                        "neighborhood": "Pinheiros",
                        "number": "100",
                        "uf": "sp",
                    },
                    "lat": -23.56,
                    "lng": -46.69,
                    "photo": [
                        {
                            "mediumUrl": "https://images.lopes.com.br/REO123456/1.jpg",
                        }
                    ],
                    "company": {"name": "Lopes"},
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sale/br/sp/sao-paulo")
        return httpx.Response(200, json=payload)

    connector = LopesConnector(httpx.Client(transport=httpx.MockTransport(handler)))
    batch = connector.search(_demand())

    assert len(batch.records) == 1
    record = batch.records[0]
    assert record.source_listing_id == "REO123456"
    assert record.price == Decimal("1250000")
    assert record.neighborhood == "Pinheiros"
    assert record.bedrooms == 3
    assert record.area == 88
    assert record.primary_image_url.endswith("/1.jpg")
    assert record.extraction_confidence == 95


def test_quintoandar_connector_reads_real_estate_json_ld() -> None:
    html = """
    <html><script type="application/ld+json">{
      "@context":"https://schema.org",
      "@type":"ItemList",
      "itemListElement":[{"@type":"ListItem","item":{
        "@type":"RealEstateListing",
        "@id":"https://www.quintoandar.com.br/imovel/895575768/comprar/apartamento",
        "name":"Apartamento com 2 dorms, 96m²",
        "url":"https://www.quintoandar.com.br/imovel/895575768/comprar/apartamento",
        "image":"https://www.quintoandar.com.br/img/sml/895575768.jpg",
        "about":{
          "@type":"Apartment",
          "numberOfBedrooms":2,
          "numberOfFullBathrooms":3,
          "floorSize":{"value":96,"unitCode":"MTK"},
          "address":{
            "streetAddress":"Rua Helena, Vila Olímpia",
            "addressLocality":"São Paulo",
            "addressRegion":"SP"
          }
        },
        "offers":{"price":1250000,"priceCurrency":"BRL"}
      }}]
    }</script></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sao-paulo-sp-brasil/apartamento")
        return httpx.Response(200, text=html)

    connector = QuintoAndarConnector(httpx.Client(transport=httpx.MockTransport(handler)))
    record = connector.search(_demand()).records[0]

    assert record.source_listing_id == "895575768"
    assert record.price == Decimal("1250000")
    assert record.neighborhood == "Vila Olímpia"
    assert record.property_type == "apartamento"
    assert record.bedrooms == 2
    assert record.bathrooms == 3
    assert record.area == 96
    assert record.primary_image_url.endswith("895575768.jpg")


def test_lello_connector_reuses_structured_parser_and_corrects_location() -> None:
    html = """
    <html><script type="application/ld+json">[{
      "idImovel":171614,
      "tipoImovel":"Apartamento",
      "bairro":"Pinheiros",
      "cidade":"São Paulo",
      "valorVenda":1200000,
      "quantidadeDormitorios":2,
      "quantidadeBanheiros":2,
      "quantidadeVagas":1,
      "metragemPrincipal":80,
      "fotos":[{"enderecoFoto":"https://cdn.lello.test/171614.webp","fotoPrincipal":true}]
    },{
      "@type":"ItemList",
      "itemListElement":[{"item":{
        "@type":"Apartment",
        "name":"Apartment",
        "url":"/imovel/171614/apartamento-pinheiros-sao-paulo-venda/",
        "offers":{"price":"1200000"},
        "numberOfBedrooms":2,
        "numberOfFullBathrooms":2,
        "floorSize":{"value":80},
        "address":{"addressLocality":"Pinheiros","addressRegion":"SP"}
      }}]
    }]</script></html>
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    connector = LelloConnector(httpx.Client(transport=httpx.MockTransport(handler)))
    record = connector.search(_demand()).records[0]

    assert record.source_listing_id == "171614"
    assert record.city == "São Paulo"
    assert record.neighborhood == "Pinheiros"
    assert record.price == Decimal("1200000")
    assert record.bedrooms == 2
    assert record.area == 80
    assert record.primary_image_url == "https://cdn.lello.test/171614.webp"
    assert record.extraction_confidence == 94


def test_connectors_expose_completeness_separately_from_fit() -> None:
    record = (
        QuintoAndarConnector(
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200,
                        text=(
                            '<script type="application/ld+json">'
                            '{"@type":"RealEstateListing","name":"Imóvel",'
                            '"url":"https://www.quintoandar.com.br/imovel/123456/comprar/imovel",'
                            '"about":{"@type":"Apartment","address":'
                            '{"addressLocality":"São Paulo","addressRegion":"SP"}},'
                            '"offers":{"price":500000}}'
                            "</script>"
                        ),
                    )
                )
            )
        )
        .search(_demand())
        .records[0]
    )

    assert 0 < record.completeness_score() < 100
