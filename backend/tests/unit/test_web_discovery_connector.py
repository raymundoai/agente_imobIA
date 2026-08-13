import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.modules.capture.connectors.base import ConnectorError
from app.modules.capture.connectors.registry import default_connector_registry
from app.modules.capture.connectors.web_discovery import WebDiscoveryConnector
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose


class _Output:
    def __init__(self, data: dict) -> None:
        self._data = data

    def model_dump(self) -> dict:
        return self._data


class _Responses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _demand() -> LeadDemand:
    return LeadDemand(
        tenant_id=uuid4(),
        lead_name="João Silva",
        phone="5551999999999",
        purpose=LeadPurpose.BUY,
        property_type="Casa",
        city="Novo Hamburgo",
        neighborhoods=["Centro", "Vila Nova"],
        price_max=Decimal("700000"),
    )


def test_web_discovery_keeps_only_grounded_new_sources_and_enriches_image() -> None:
    local_url = "https://localimoveis.com.br/imovel/casa-vila-nova-123456"
    payload = {
        "results": [
            {
                "url": f"{local_url}?utm_source=openai",
                "title": "Casa com piscina na Vila Nova",
                "city": "Novo Hamburgo",
                "state": "RS",
                "neighborhood": "Vila Nova",
                "property_type": "Casa",
                "sale_price": 650000,
                "rent_price": None,
                "bedrooms": 3,
                "bathrooms": 2,
                "parking_spaces": 2,
                "area": 180,
                "primary_image_url": None,
                "advertiser_name": "Imobiliária Local",
            },
            {
                "url": "https://www.olx.com.br/imovel/casa-654321",
                "title": "Fonte já tratada",
                "city": "Novo Hamburgo",
                "state": "RS",
                "neighborhood": "Centro",
                "property_type": "Casa",
                "sale_price": 500000,
                "rent_price": None,
                "bedrooms": 2,
                "bathrooms": 1,
                "parking_spaces": 1,
                "area": 100,
                "primary_image_url": None,
                "advertiser_name": None,
            },
            {
                "url": "https://semcitacao.com.br/imovel/999999",
                "title": "Resultado não fundamentado",
                "city": "Novo Hamburgo",
                "state": "RS",
                "neighborhood": "Centro",
                "property_type": "Casa",
                "sale_price": 400000,
                "rent_price": None,
                "bedrooms": 2,
                "bathrooms": 1,
                "parking_spaces": 1,
                "area": 90,
                "primary_image_url": None,
                "advertiser_name": None,
            },
        ]
    }
    usage = SimpleNamespace(
        input_tokens=50_000,
        output_tokens=1_500,
        input_tokens_details=SimpleNamespace(cached_tokens=5_000),
    )
    response = SimpleNamespace(
        output_text=json.dumps(payload),
        output=[
            _Output(
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {"url": "https://localimoveis.com.br/busca/novo-hamburgo"},
                            {"url": "https://www.olx.com.br/imovel/casa-654321"},
                        ]
                    },
                }
            )
        ],
        usage=usage,
    )
    responses = _Responses(response)
    openai_client = SimpleNamespace(responses=responses)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == local_url
        return httpx.Response(
            200,
            text=(
                '<link rel="canonical" href="https://localimoveis.com.br/imovel/'
                'casa-vila-nova-123456">'
                '<meta property="og:image" content="https://cdn.localimoveis.com.br/123456.jpg">'
            ),
        )

    connector = WebDiscoveryConnector(
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_key="test-key",
        openai_client=openai_client,
    )
    batch = connector.search(_demand())

    assert len(batch.records) == 1
    record = batch.records[0]
    assert record.canonical_url == local_url
    assert record.sale_price == Decimal("650000")
    assert record.price == Decimal("650000")
    assert record.purpose == "buy"
    assert record.primary_image_url == "https://cdn.localimoveis.com.br/123456.jpg"
    assert record.advertiser_name == "Imobiliária Local"
    assert record.raw_data["source_domain"] == "localimoveis.com.br"
    assert record.raw_data["grounding"] == "verified_source_domain"
    assert record.raw_data["page_verified"] is True
    assert record.raw_data["usage"]["input_tokens"] == 50_000
    assert responses.kwargs["model"] == "gpt-5.6-luna"
    assert responses.kwargs["tools"][0]["search_context_size"] == "low"
    assert "Novo Hamburgo/RS" in responses.kwargs["input"]


def test_web_discovery_rejects_listing_redirected_to_a_generic_page() -> None:
    listing_url = "https://localimoveis.com.br/imovel/casa-123456"
    payload = {
        "results": [
            {
                "url": listing_url,
                "title": "Casa indisponível",
                "city": "Novo Hamburgo",
                "state": "RS",
                "neighborhood": "Centro",
                "property_type": "Casa",
                "sale_price": 500000,
                "rent_price": None,
                "bedrooms": None,
                "bathrooms": None,
                "parking_spaces": None,
                "area": None,
                "primary_image_url": None,
                "advertiser_name": None,
            }
        ]
    }
    response = SimpleNamespace(
        output_text=json.dumps(payload),
        output=[
            _Output(
                {
                    "type": "web_search_call",
                    "action": {"sources": [{"url": listing_url}]},
                }
            )
        ],
        usage=None,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/imovel/casa-123456":
            return httpx.Response(302, headers={"location": "/imoveis/venda"})
        return httpx.Response(200, text="Página genérica")

    connector = WebDiscoveryConnector(
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_key="test-key",
        openai_client=SimpleNamespace(responses=_Responses(response)),
    )

    assert connector.search(_demand()).records == []


def test_registry_adds_web_discovery_only_when_enabled_and_configured() -> None:
    client = httpx.Client()
    without_key = default_connector_registry(client, web_discovery_enabled=True)
    with_key = default_connector_registry(
        client,
        web_discovery_enabled=True,
        openai_api_key="test-key",
    )

    assert "web_discovery" not in {item.id for item in without_key.descriptors()}
    assert "web_discovery" in {item.id for item in with_key.descriptors()}
    descriptor = with_key.get("web_discovery").descriptor
    assert descriptor.automatic is False
    assert descriptor.premium is True


def test_web_discovery_keeps_usage_when_structured_output_is_invalid() -> None:
    usage = SimpleNamespace(
        input_tokens=1200,
        output_tokens=80,
        input_tokens_details=SimpleNamespace(cached_tokens=200),
    )
    connector = WebDiscoveryConnector(
        httpx.Client(),
        api_key="test-key",
        openai_client=SimpleNamespace(
            responses=_Responses(
                SimpleNamespace(output_text="", output=[], usage=usage)
            )
        ),
    )

    with pytest.raises(ConnectorError):
        connector.search(_demand())

    assert connector.last_usage == {
        "input_tokens": 1200,
        "cached_input_tokens": 200,
        "output_tokens": 80,
    }
