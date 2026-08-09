import html as html_lib
import json
from decimal import Decimal
from uuid import uuid4

import httpx

from app.modules.capture.connectors.auxiliadora_predial import AuxiliadoraPredialConnector
from app.modules.capture.connectors.imoveis_diferenciados import ImoveisDiferenciadosConnector
from app.modules.capture.connectors.nova_sao_paulo import NovaSaoPauloConnector
from app.modules.capture.connectors.ohi import OhiConnector
from app.modules.capture.connectors.registry import default_connector_registry
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose


def _demand(city: str, purpose: LeadPurpose = LeadPurpose.RENT) -> LeadDemand:
    return LeadDemand(
        tenant_id=uuid4(),
        lead_name="Teste",
        phone="5551999999999",
        purpose=purpose,
        property_type="apartamento",
        city=city,
        neighborhoods=["Pinheiros" if city == "São Paulo" else "Petrópolis"],
        price_max=Decimal("5000" if purpose == LeadPurpose.RENT else "1500000"),
        bedrooms=2,
        parking_spaces=1,
    )


def test_auxiliadora_reads_real_estate_listing_and_ignores_empty_placeholder() -> None:
    html = """
    <script type="application/ld+json">[{
      "@type":"RealEstateListing",
      "@id":"https://www.auxiliadorapredial.com.br/imovel/alugar/302967",
      "url":"https://www.auxiliadorapredial.com.br/imovel/alugar/302967",
      "identifier":"302967",
      "name":"Apartamento - Azenha - Porto Alegre",
      "image":{"contentUrl":"https://cdn.aux.test/302967.jpg"},
      "offers":[{
        "price":2950,
        "itemOffered":{
          "@type":"Accommodation",
          "accommodationCategory":"Apartamento",
          "address":{"streetAddress":"Rua Teste","addressLocality":"Porto Alegre"},
          "geo":{"latitude":"-30.05","longitude":"-51.21"},
          "floorSize":{"value":87},
          "numberOfBedrooms":2,
          "numberOfBathroomsTotal":1,
          "amenityFeature":[{"name":"Vagas de Garagem","value":"1"}]
        }
      }]
    },{
      "@type":"RealEstateListing",
      "url":"https://www.auxiliadorapredial.com.br/imovel/alugar/null",
      "name":"Imóvel"
    }]</script>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/alugar/residencial/rs+porto-alegre"
        return httpx.Response(200, text=html)

    connector = AuxiliadoraPredialConnector(httpx.Client(transport=httpx.MockTransport(handler)))
    batch = connector.search(_demand("Porto Alegre"))

    assert len(batch.records) == 1
    record = batch.records[0]
    assert record.source_listing_id == "302967"
    assert record.price == Decimal("2950")
    assert record.rent_price == Decimal("2950")
    assert record.neighborhood == "Azenha"
    assert record.bedrooms == 2
    assert record.bathrooms == 1
    assert record.parking_spaces == 1
    assert record.area == 87
    assert record.primary_image_url == "https://cdn.aux.test/302967.jpg"


def test_nova_sao_paulo_applies_rent_filters_and_parses_card() -> None:
    shared = html_lib.escape(
        json.dumps(
            {
                "id": "AB12345",
                "title": "Apartamento em Pinheiros",
                "description": "Bem iluminado",
                "image": "https://cdn.nova.test/AB12345.jpg",
                "url": (
                    "https://www.novasaopaulo.com.br/imovel/apartamento/locacao/"
                    "sao-paulo/pinheiros/AB12345"
                ),
            }
        ),
        quote=True,
    )
    page = f"""
    <article class="flex card">
      <a href="https://www.novasaopaulo.com.br/imovel/apartamento/locacao/sao-paulo/pinheiros/AB12345">
        <img src="https://cdn.nova.test/AB12345.jpg">
      </a>
      <button data-share="{shared}"></button>
      <strong class="font-serif">Pinheiros</strong>
      <label><span>Locação</span> R$ 4.500</label>
      <label><span>Venda</span> R$ 900.000</label>
      <p class="overflow-hidden">Rua dos Pinheiros, 100</p>
      <span>80m² Útil</span><span>2 Quartos</span><span>1 Vaga</span>
    </article>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["negotiation"] == "locacao"
        assert request.url.params["value_max"] == "5000"
        assert request.url.params["bedrooms[]"] == "2"
        assert request.url.params["garages[]"] == "1"
        return httpx.Response(200, text=page)

    connector = NovaSaoPauloConnector(httpx.Client(transport=httpx.MockTransport(handler)))
    record = connector.search(_demand("São Paulo")).records[0]

    assert record.source_listing_id == "AB12345"
    assert record.price == Decimal("4500")
    assert record.rent_price == Decimal("4500")
    assert record.sale_price == Decimal("900000")
    assert record.purpose == "both"
    assert record.neighborhood == "Pinheiros"
    assert record.bedrooms == 2
    assert record.parking_spaces == 1
    assert record.area == 80


def test_ohi_keeps_sale_price_as_alternative_on_rental_search() -> None:
    html = """
    <a class="ohi-card"
       href="/imovel/sao-paulo/pinheiros/condominio/apartamento/2-quartos/oh29244"
       aria-label="Rua Pais Leme, 215">
      <img class="ohi-card__img" src="https://cdn.ohi.test/oh29244.jpg">
      <span class="ohi-card__neigh">Pinheiros</span>
      <span class="ohi-card__code">OH29244</span>
      <span class="ohi-card__price">R$ 8.500 <small>/mês</small></span>
      <span class="ohi-card__price-alt-label">Venda</span>
      <span class="ohi-card__price-alt-val">R$ 1.696.000</span>
      <div class="ohi-card__facts">
        <span class="ohi-card__fact">77m²</span>
        <span class="ohi-card__fact">2</span>
        <span class="ohi-card__fact">2 banheiros</span>
        <span class="ohi-card__fact">1</span>
      </div>
      <div class="ohi-card__costs">Cond. R$ 1.150</div>
    </a>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["mode"] == "rent"
        assert request.url.params["q"] == "Pinheiros"
        return httpx.Response(200, text=html)

    connector = OhiConnector(httpx.Client(transport=httpx.MockTransport(handler)))
    record = connector.search(_demand("São Paulo")).records[0]

    assert record.source_listing_id == "OH29244"
    assert record.price == Decimal("8500")
    assert record.rent_price == Decimal("8500")
    assert record.sale_price == Decimal("1696000")
    assert record.purpose == "both"
    assert record.bedrooms == 2
    assert record.bathrooms == 2
    assert record.parking_spaces == 1
    assert record.area == 77
    assert record.condominium_fee == Decimal("1150")


def test_imoveis_diferenciados_uses_tecimob_api_with_domain_header() -> None:
    payload = {
        "data": [
            {
                "id": "property-uuid",
                "reference": "SBF-CA-02",
                "price": "R$ 1.750",
                "transaction": "ALUGUEL",
                "address": {"formatted": "Caminho das Árvores - Salvador/BA"},
                "areas": {"private_area": {"value": "30"}},
                "rooms": {
                    "bedroom": {"value": 1},
                    "bathroom": {"value": 1},
                    "garage": {"value": 1},
                },
                "meta_title": "Apartamento para alugar em Salvador",
                "title_formatted": "Apartamento com 30m²",
                "url": "apartamento-para-alugar-em-salvador-ba/SBF-CA-02",
                "images": [{"file_url": {"medium": "https://cdn.tecimob.test/property.webp"}}],
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-domain"] == "imoveisdiferenciados.com.br"
        assert request.url.params["filter[transaction]"] == "2"
        assert request.url.params["limit"] == "24"
        return httpx.Response(200, json=payload)

    connector = ImoveisDiferenciadosConnector(httpx.Client(transport=httpx.MockTransport(handler)))
    record = connector.search(_demand("Salvador")).records[0]

    assert record.source_listing_id == "SBF-CA-02"
    assert record.price == Decimal("1750")
    assert record.rent_price == Decimal("1750")
    assert record.city == "Salvador"
    assert record.state == "BA"
    assert record.neighborhood == "Caminho das Árvores"
    assert record.property_type == "Apartamento"
    assert record.bedrooms == 1
    assert record.parking_spaces == 1
    assert record.area == 30


def test_registry_exposes_new_sources_only_in_their_real_coverage() -> None:
    registry = default_connector_registry(httpx.Client())

    sp_sources = {item.id for item in registry.available_for(_demand("São Paulo"))}
    ba_sources = {item.id for item in registry.available_for(_demand("Salvador"))}

    assert {"auxiliadora_predial", "nova_sao_paulo", "ohi"} <= sp_sources
    assert "imoveis_diferenciados" not in sp_sources
    assert "imoveis_diferenciados" in ba_sources
