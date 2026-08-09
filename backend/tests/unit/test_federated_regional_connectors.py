import json
from decimal import Decimal
from uuid import uuid4

import httpx

from app.modules.capture.connectors.bridge import BridgeConnector
from app.modules.capture.connectors.chaves_na_mao import ChavesNaMaoConnector
from app.modules.capture.connectors.foxter import FoxterConnector
from app.modules.capture.connectors.guarida import GuaridaConnector
from app.modules.capture.connectors.refugios_urbanos import RefugiosUrbanosConnector
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose


def _demand(
    *,
    city: str = "Porto Alegre",
    purpose: LeadPurpose = LeadPurpose.BUY,
    neighborhoods: list[str] | None = None,
) -> LeadDemand:
    return LeadDemand(
        tenant_id=uuid4(),
        lead_name="Teste",
        phone="5551999999999",
        purpose=purpose,
        property_type="apartamento",
        city=city,
        neighborhoods=neighborhoods or [],
        price_max=Decimal("1500000"),
        bedrooms=2,
    )


def _client(body: str) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body)))


def test_guarida_connector_reads_next_data() -> None:
    payload = {
        "props": {
            "pageProps": {
                "search": {
                    "imoveis": [
                        {
                            "negocio": "comprar",
                            "finalidade": "residencial",
                            "tipo": {"nome": "Apartamento"},
                            "codigo": "810822",
                            "titulo": "Apartamento no Menino Deus",
                            "endereco": "Menino Deus, Porto Alegre - RS",
                            "logradouro": "Rua Gonçalves Dias, 1075",
                            "latitude": "-30.05",
                            "longitude": "-51.22",
                            "valores": {
                                "valor": "R$ 980.000",
                                "condominio": "R$ 700",
                                "iptu": "R$ 1.900",
                            },
                            "fotos": [{"url": "https://images.test/810822.jpg"}],
                            "propriedades": [
                                {"slug": "dormitorios", "valor": "3"},
                                {"slug": "banheiro", "valor": "2"},
                                {"slug": "vaga", "valor": "2"},
                                {"slug": "area", "valor": "86"},
                            ],
                            "url": "/imovel/comprar/menino-deus/apartamento/810822",
                        }
                    ]
                }
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    record = GuaridaConnector(_client(html)).search(_demand()).records[0]

    assert record.source_listing_id == "810822"
    assert record.neighborhood == "Menino Deus"
    assert record.price == Decimal("980000")
    assert record.bedrooms == 3
    assert record.area == 86
    assert record.primary_image_url == "https://images.test/810822.jpg"


def test_foxter_connector_reads_next_data() -> None:
    payload = {
        "props": {
            "pageProps": {
                "results": [
                    {
                        "code": 694262,
                        "state": "RS",
                        "district": "São Geraldo",
                        "city": "Porto Alegre",
                        "place": "Avenida São Pedro",
                        "images": {"data": [{"etag": "Product/694262/pictures/01.jpg"}]},
                        "price": "585.000,00",
                        "areaPrivate": "80",
                        "bedrooms": 2,
                        "bathrooms": 1,
                        "parkingSpaces": 1,
                        "type": "Apartamento",
                        "title": "Apartamento com 2 dormitórios à venda",
                        "condominiumAmountValue": "R$ 850,00",
                    }
                ]
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    record = FoxterConnector(_client(html)).search(_demand()).records[0]

    assert record.source_listing_id == "694262"
    assert record.price == Decimal("585000.00")
    assert record.neighborhood == "São Geraldo"
    assert record.area == 80
    assert record.primary_image_url.endswith("Product/694262/pictures/01.jpg")


def test_bridge_connector_correlates_json_ld_with_card_url() -> None:
    html = """
    <script type="application/ld+json">{
      "@type":"ItemList",
      "itemListElement":[{"item":{
        "@type":"Product",
        "name":"Apartamento, 94m² - Petrópolis, POA/RS - 51004",
        "description":"Apartamento com 2 dormitórios, 2 banheiros e 1 vaga.",
        "image":"https://images.test/51004.jpg",
        "offers":{"price":950000,"seller":{"name":"Bridge","telephone":"+555130149600"}}
      }}]
    }</script>
    <div data-url="https://www.bridgeimoveis.com.br/imovel/51004/apartamento-petropolis"></div>
    """
    record = BridgeConnector(_client(html)).search(_demand()).records[0]

    assert record.source_listing_id == "51004"
    assert record.canonical_url.endswith("/51004/apartamento-petropolis")
    assert record.neighborhood == "Petrópolis"
    assert record.price == Decimal("950000")
    assert record.bedrooms == 2
    assert record.parking_spaces == 1
    assert record.area == 94


def test_chaves_na_mao_connector_reads_offer_item() -> None:
    html = """
    <script type="application/ld+json">{
      "@type":"RealEstateListing",
      "offers":{"@type":"ItemList","itemListElement":[{
        "@type":"Offer",
        "name":"Apartamento com 2 quartos e 1 vaga à venda",
        "url":"https://www.chavesnamao.com.br/imovel/apartamento/id-45077334/",
        "price":"650000",
        "itemOffered":{
          "@type":"Apartment","numberOfBedrooms":2,"numberOfBathroomsTotal":1,
          "floorSize":{"unitText":"80m²"},
          "address":{"addressLocality":"Petrópolis","streetAddress":"Rua Felizardo"},
          "geo":{"latitude":"-30.04","longitude":"-51.19"},
          "image":"https://images.test/45077334.jpg"
        },
        "offeredBy":{"name":"Imobiliária parceira"}
      }]}
    }</script>
    """
    record = ChavesNaMaoConnector(_client(html)).search(_demand()).records[0]

    assert record.source_listing_id == "45077334"
    assert record.neighborhood == "Petrópolis"
    assert record.property_type == "apartamento"
    assert record.area == 80
    assert record.primary_image_url.endswith("45077334.jpg")


def test_refugios_connector_reads_structured_cards() -> None:
    html = """
    <article class="imovel imovel-unico imovel-unico--ape">
      <a href="https://refugiosurbanos.com.br/imoveis/apartamento-reformado-em-pinheiros/">
        <img src="placeholder.svg" data-lazy-src="https://images.test/refugio.jpg">
      </a>
      <p class="pull-left">
        <a href="https://refugiosurbanos.com.br/imoveis/apartamento-reformado-em-pinheiros/">
          Apartamento reformado em Pinheiros
        </a>
      </p>
      <p class="pull-right preco-imovel">R$ 1.280.000,00</p>
      <p class="composicao">89 m<sup>2</sup> / 3 Quartos / 2 Banheiros / 1 Vaga</p>
      <p style="color: #ea8332;">RU: 10049 - Pinheiros</p>
    </article>
    """
    demand = _demand(city="São Paulo", neighborhoods=["Pinheiros"])
    record = RefugiosUrbanosConnector(_client(html)).search(demand).records[0]

    assert record.source_listing_id == "10049"
    assert record.neighborhood == "Pinheiros"
    assert record.price == Decimal("1280000.00")
    assert record.bedrooms == 3
    assert record.area == 89
    assert record.primary_image_url == "https://images.test/refugio.jpg"
