import json
from decimal import Decimal
from uuid import uuid4

import httpx

from app.modules.capture.connectors.dapper import DapperConnector
from app.modules.capture.connectors.delta import DeltaConnector
from app.modules.capture.connectors.rede_gaucha import RedeGauchaConnector
from app.modules.capture.connectors.registry import default_connector_registry
from app.modules.capture.connectors.terramar import TerramarConnector
from app.modules.capture.connectors.urban import UrbanConnector
from app.modules.capture.connectors.vendas_rs import VendasRSConnector
from app.modules.capture.connectors.vila_rica import VilaRicaConnector
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose


def _demand(
    *, city: str = "Porto Alegre", purpose: LeadPurpose = LeadPurpose.BUY
) -> LeadDemand:
    return LeadDemand(
        tenant_id=uuid4(),
        lead_name="Teste",
        phone="5551999999999",
        purpose=purpose,
        property_type="apartamento",
        city=city,
        neighborhoods=["Auxiliadora"],
        bedrooms=2,
    )


def _client(body: str, *, content_type: str = "text/html") -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=body, headers={"content-type": content_type})
        )
    )


def test_urban_connector_reads_property_cards() -> None:
    html = """
    <section id="search-results">
      <a href="https://www.urban.imb.br/imovel/36798/apartamento"
         class="property-listing" data-codigo="36798">
        <img src="https://images.test/36798.webp">
        <p class="category">Apartamento com 2 quartos</p>
        <p class="location"><span class="street">R. Coronel Bordini,</span>
          <strong>Auxiliadora</strong>, Porto Alegre</p>
        <div class="numbers"><p>2 quartos</p><p>88m²</p><p>1 vaga</p></div>
        <p class="price text-gradient">R$ 850.000</p>
      </a>
    </section>
    """
    record = UrbanConnector(_client(html)).search(_demand()).records[0]

    assert record.source_listing_id == "36798"
    assert record.neighborhood == "Auxiliadora"
    assert record.sale_price == Decimal("850000")
    assert record.bedrooms == 2
    assert record.parking_spaces == 1
    assert record.area == 88


def test_urban_connector_treats_confirmed_empty_catalog_as_success() -> None:
    html = """
    <meta name="description" content="Veja 0 casas à venda Novo Hamburgo.">
    <section id="search-results" class="properties-wrapper">
    </section>
    """

    batch = UrbanConnector(_client(html)).search(_demand(city="Novo Hamburgo"))

    assert batch.records == []


def test_terramar_connector_reads_prices_and_amenities() -> None:
    html = """
    <div class="col-xs-12 imovel-box-single" data-codigo="5525">
      <a href="https://terramar.com.br/imovel/5525/apartamento-centro/">
        <div class="foto-imovel" style="background-image: url(https://images.test/5525.jpg);"></div>
      </a>
      <h2 class="titulo-grid">Apartamento 2 Quartos Centro 204m²</h2>
      <h3 itemprop="streetAddress">Rua Augusto Jung, 180, Centro - Novo Hamburgo/Rs</h3>
      <span class="property-thumb-item"><span class="thumb-status">Venda</span>
        <span class="thumb-price">R$ 3.500.000,00</span></span>
      <div class="property-amenities">
        <div><span>2</span><small>Quartos</small></div>
        <div><span>2</span><small>Suítes</small></div>
        <div><span>3</span><small>Vagas</small></div>
        <div><span>204<font>m²</font></span><small>Privat.</small></div>
      </div>
    </div>
    """
    record = TerramarConnector(_client(html)).search(_demand(city="Novo Hamburgo")).records[0]

    assert record.source_listing_id == "5525"
    assert record.city == "Novo Hamburgo"
    assert record.neighborhood == "Centro"
    assert record.sale_price == Decimal("3500000.00")
    assert record.bedrooms == 2
    assert record.suites == 2
    assert record.parking_spaces == 3
    assert record.area == 204


def test_terramar_treats_redirect_for_city_outside_catalog_as_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/":
            return httpx.Response(302, headers={"location": "/"})
        return httpx.Response(200, text="<html>Página inicial</html>")

    connector = TerramarConnector(
        httpx.Client(transport=httpx.MockTransport(handler))
    )

    assert connector.search(_demand(city="Porto Alegre")).records == []


def test_rede_gaucha_connector_reads_public_api_and_cents() -> None:
    payload = {
        "totalItems": 1,
        "items": [
            {
                "id": 9818451,
                "code": "33768-TR",
                "url": "/imovel/casa/33768-TR",
                "title": "Casa com 2 quartos à venda",
                "description": "Casa no bairro Morada do Bosque",
                "type": "Casa",
                "garage": 2,
                "bedrooms": 2,
                "bathrooms": 1,
                "suites": 0,
                "address": {
                    "street": "Rua Otto Espíndola",
                    "neighborhood": "Morada do Bosque",
                    "city": "Cachoeirinha",
                    "state": "RS",
                    "coordinate": {"latitude": "-29.90", "longitude": "-51.08"},
                },
                "contracts": [{"id": 1, "price": {"value": 29000000}}],
                "usefulArea": {"value": 50},
                "terrainArea": {"value": 120},
                "images": [{"src": "https://images.test/33768.jpg"}],
            }
        ],
    }
    record = (
        RedeGauchaConnector(_client(json.dumps(payload), content_type="application/json"))
        .search(_demand(city="Cachoeirinha"), limit=1)
        .records[0]
    )

    assert record.source_listing_id == "33768-TR"
    assert record.sale_price == Decimal("290000")
    assert record.area == 50
    assert record.land_area == 120
    assert record.primary_image_url.endswith("33768.jpg")


def test_delta_connector_reads_graphql_prices_and_location() -> None:
    payload = {
        "data": {
            "imoveis_busca": {
                "count": 1,
                "imoveis": [
                    {
                        "id": 3700960,
                        "referencia": "5833",
                        "titulo": "Apartamento semimobiliado com 2 quartos",
                        "descricao": "Apartamento no bairro Vila Rosa",
                        "venda": True,
                        "aluguel": False,
                        "tipo": {"nome": "Apartamento", "id": 1},
                        "categoria": {"nome": "Mobiliado", "id": 10022},
                        "cidade": {"nome": "Novo Hamburgo", "id": 19571},
                        "bairro": {"nome": "Vila Rosa", "id": 121431},
                        "dormitorios": 2,
                        "suites": 0,
                        "banheiros": 1,
                        "garagems": 1,
                        "preco_venda": 315000,
                        "preco_locacao": 0,
                        "area_total": None,
                        "area_privativa": 43,
                        "area_util": None,
                        "terreno": None,
                        "fotos": {"url_foto": "https://images.test/3700960.jpg"},
                        "preco_especial": None,
                    }
                ],
            }
        }
    }
    record = (
        DeltaConnector(_client(json.dumps(payload), content_type="application/json"))
        .search(_demand(city="Novo Hamburgo"), limit=1)
        .records[0]
    )

    assert record.source_listing_id == "3700960"
    assert record.city == "Novo Hamburgo"
    assert record.neighborhood == "Vila Rosa"
    assert record.sale_price == Decimal("315000")
    assert record.area == 43
    assert record.primary_image_url.endswith("3700960.jpg")


def test_dapper_connector_reads_public_catalog_and_applies_demand_filters() -> None:
    payload = {
        "CurrentPage": 1,
        "NumberOfItems": 1,
        "Items": [
            {
                "Id": "6396",
                "ReferenceId": "V14460",
                "Image": "/Content/Artifacts/RealEstate/Realty/6396.jpg",
                "Title": "CASA 2 Dormitórios",
                "Description": "Casa com pátio no bairro Hamburgo Velho.",
                "Price": 500000,
                "CurrentRealtyTypeTitle": "Casa",
                "CurrentNegotiationTypeId": "2",
                "Bedrooms": 2,
                "Suites": 1,
                "Bathrooms": 2,
                "ParkingSpots": 2,
                "Area": 130.5,
                "LotArea": 301.6,
                "IPTUValue": 1200,
                "CondominiumValue": 0,
                "Photos": [
                    {"Path": "/Content/Artifacts/RealEstate/Realty/6396.jpg"}
                ],
                "CurrentSpot": {
                    "Latitude": -2968091919999999,
                    "Longitude": -51106893600000032,
                    "CurrentStateName": "RS",
                    "City": "Novo Hamburgo",
                    "Neighborhood": "Hamburgo Velho",
                    "CurrentAddress": "Rua Vinícius de Moraes",
                    "Number": "147",
                    "ZipCode": "93540-240",
                },
            }
        ],
        "Error": False,
    }
    requested_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(request.url)
        return httpx.Response(200, json=payload)

    demand = _demand(city="Novo Hamburgo")
    demand.property_type = "casa"
    demand.neighborhoods = ["Hamburgo Velho"]
    demand.price_min = Decimal("300000")
    demand.price_max = Decimal("600000")
    demand.parking_spaces = 2
    record = DapperConnector(
        httpx.Client(transport=httpx.MockTransport(handler))
    ).search(demand, limit=12).records[0]

    query = requested_urls[0].params
    assert query["nt"] == "2"
    assert query["tipo_imovel"] == "54"
    assert query["cidade"] == "Novo Hamburgo"
    assert query["bairros"] == "Hamburgo Velho"
    assert query["valor_de"] == "300000"
    assert query["valor_ate"] == "600000"
    assert query["vagas"] == "2"
    assert query["pageSize"] == "12"
    assert record.source_listing_id == "6396"
    assert record.canonical_url == "https://dapperimoveis.com.br/imovel/V14460"
    assert record.purpose == "buy"
    assert record.sale_price == Decimal("500000")
    assert record.rent_price is None
    assert record.neighborhood == "Hamburgo Velho"
    assert record.bedrooms == 2
    assert record.area == 130
    assert record.latitude == Decimal("-29.68091919999999")
    assert record.primary_image_url.endswith("/RealEstate/Realty/6396.jpg")


def test_dapper_connector_keeps_rent_separate_from_sale() -> None:
    payload = {
        "Items": [
            {
                "Id": "21243",
                "ReferenceId": "L14654",
                "Title": "Pavilhão para locação",
                "Price": 90000,
                "CurrentRealtyTypeTitle": "Pavilhao/Deposito",
                "CurrentNegotiationTypeId": "1",
                "Photos": [],
                "CurrentSpot": {
                    "CurrentStateName": "RS",
                    "City": "Novo Hamburgo",
                    "Neighborhood": "Santo Afonso",
                },
            }
        ],
        "Error": False,
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    record = DapperConnector(client).search(
        _demand(city="Novo Hamburgo", purpose=LeadPurpose.RENT), limit=1
    ).records[0]

    assert record.purpose == "rent"
    assert record.price == Decimal("90000")
    assert record.rent_price == Decimal("90000")
    assert record.sale_price is None


def test_registry_exposes_dapper_only_for_rs_demands() -> None:
    registry = default_connector_registry(httpx.Client())

    rs_sources = {item.id for item in registry.available_for(_demand(city="Novo Hamburgo"))}
    sp_sources = {item.id for item in registry.available_for(_demand(city="São Paulo"))}

    assert "dapper" in rs_sources
    assert "dapper" not in sp_sources


def test_vendas_rs_connector_reads_public_paged_endpoint() -> None:
    body = """
    <div class="artigo__listapaginas__item">
      <a href="/apartamento-308-vila-joao-pessoa-porto-alegre">
        <img src="/upload/recortes/apartamento_MD.jpg">
      </a>
      <a class="label label-warning">Apartamento</a>
      <h3 class="artigo__listapaginas__item__titulo">
        <a>Apartamento 308 - Vila João Pessoa, Porto Alegre</a>
      </h3>
      <p class="artigo__listapaginas__item__descricao">Porto Alegre - RS</p>
      <p class="artigo__listapaginas__item__valor">R$ 103.000,00</p>
    </div>
    """
    payload = json.dumps({"recordcount": 1, "body": body})
    record = (
        VendasRSConnector(_client(payload, content_type="application/json"))
        .search(_demand(), limit=1)
        .records[0]
    )

    assert record.property_type == "Apartamento"
    assert record.neighborhood == "Vila João Pessoa"
    assert record.sale_price == Decimal("103000.00")
    assert record.primary_image_url.endswith("apartamento_MD.jpg")


def test_vila_rica_connector_reads_vista_catalog() -> None:
    payload = {
        "VR36386": {
            "Codigo": "VR36386",
            "Cidade": "Porto Alegre",
            "Bairro": "Passo da Areia",
            "BairroComercial": "Passo da Areia",
            "ValorVenda": "890000",
            "ValorLocacao": "0",
            "Dormitorios": "2",
            "Suites": "1",
            "BanheiroSocialQtd": "1",
            "Vagas": "1",
            "AreaTotal": "0",
            "AreaPrivativa": "74.24",
            "Categoria": "Apartamento",
            "Status": "Venda",
            "TituloSite": "",
            "Endereco": "Avenida João Wallig",
            "Latitude": "-30.01",
            "Longitude": "-51.16",
            "FotoDestaque": "https://images.test/VR36386.jpg",
        }
    }
    record = (
        VilaRicaConnector(_client(json.dumps(payload), content_type="application/json"))
        .search(_demand(), limit=1)
        .records[0]
    )

    assert record.source_listing_id == "VR36386"
    assert record.neighborhood == "Passo da Areia"
    assert record.sale_price == Decimal("890000")
    assert record.bedrooms == 2
    assert record.area == 74
    assert record.primary_image_url.endswith("VR36386.jpg")
