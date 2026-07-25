import httpx
import pytest

from app.modules.capture.discovery import PortalDiscoveryAdapter, parse_public_listing_html


def test_parses_public_json_ld_without_description_images_or_contacts() -> None:
    html = """
    <html><script type="application/ld+json">
    {"@type":"ItemList","itemListElement":[{"item":{
      "name":"Apartamento em Pinheiros", "url":"/imovel/123",
      "offers":{"price":"850000"}, "floorSize":{"value":"74 m²"},
      "numberOfRooms":2, "address":{"addressLocality":"São Paulo","addressRegion":"Pinheiros"},
      "description":"texto que não deve ser importado", "telephone":"11999999999"
    }}]}
    </script></html>
    """

    results = parse_public_listing_html("lello", "https://www.lelloimoveis.com.br/busca", html)

    assert len(results) == 1
    assert results[0].source_url == "https://www.lelloimoveis.com.br/imovel/123"
    assert results[0].price == "850000"
    assert results[0].area == 74
    assert not hasattr(results[0], "description")
    assert not hasattr(results[0], "telephone")


def test_parser_falls_back_to_public_listing_links() -> None:
    html = (
        '<a href="/sao-paulo/imoveis/apartamento-pinheiros-123456789">'
        "Apartamento em Pinheiros R$ 800.000</a>"
    )

    results = parse_public_listing_html("olx", "https://www.olx.com.br/imoveis", html)

    assert len(results) == 1
    assert results[0].source == "olx"
    assert results[0].source_url.endswith("-123456789")


def test_adapter_stops_when_portal_blocks_automation() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    adapter = PortalDiscoveryAdapter(httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(RuntimeError, match="recusou"):
        adapter.discover("olx", "https://www.olx.com.br/imoveis")


def test_adapter_rejects_cross_portal_url() -> None:
    adapter = PortalDiscoveryAdapter(httpx.Client())

    with pytest.raises(ValueError, match="does not match"):
        adapter.discover("olx", "https://example.com/imoveis")
