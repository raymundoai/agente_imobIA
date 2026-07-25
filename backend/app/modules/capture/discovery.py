from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

SUPPORTED_DISCOVERY_PORTALS = {"lello", "olx"}
PORTAL_HOSTS = {
    "lello": "www.lelloimoveis.com.br",
    "olx": "www.olx.com.br",
}


@dataclass(frozen=True, slots=True)
class DiscoveredProperty:
    source: str
    source_url: str
    title: str
    city: str
    neighborhood: str | None = None
    price: str | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    parking_spaces: int | None = None
    area: int | None = None


class _PublicDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._script_type = ""
        self._script_parts: list[str] | None = None
        self._href: str | None = None
        self._link_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script":
            self._script_type = attributes.get("type") or ""
            self._script_parts = []
        elif tag == "a" and attributes.get("href"):
            self._href = attributes["href"]
            self._link_parts = []

    def handle_data(self, data: str) -> None:
        if self._script_parts is not None:
            self._script_parts.append(data)
        if self._link_parts is not None:
            self._link_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script_parts is not None:
            if (
                self._script_type == "application/ld+json"
                or self._script_type == "application/json"
            ):
                self.scripts.append("".join(self._script_parts))
            self._script_parts = None
        elif tag == "a" and self._href and self._link_parts is not None:
            text = " ".join("".join(self._link_parts).split())
            if text:
                self.links.append((self._href, text))
            self._href = None
            self._link_parts = None


class PortalDiscoveryAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def discover(self, portal: str, url: str, *, limit: int = 20) -> list[DiscoveredProperty]:
        if portal not in SUPPORTED_DISCOVERY_PORTALS:
            raise ValueError("Portal is not enabled for automatic discovery")
        if urlparse(url).hostname != PORTAL_HOSTS[portal]:
            raise ValueError("Portal URL does not match the selected source")
        response = self._client.get(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "ImobIA-Discovery/0.1 (+referenced-property-search)",
            },
            follow_redirects=True,
        )
        if response.status_code in {401, 403, 429}:
            raise RuntimeError(
                "O portal recusou a leitura automática; nenhuma tentativa adicional foi feita"
            )
        response.raise_for_status()
        return parse_public_listing_html(portal, str(response.url), response.text, limit=limit)


def parse_public_listing_html(
    portal: str, base_url: str, html: str, *, limit: int = 20
) -> list[DiscoveredProperty]:
    parser = _PublicDataParser()
    parser.feed(html)
    candidates: list[dict[str, Any]] = []
    for script in parser.scripts:
        try:
            _walk_json(json.loads(script), candidates)
        except (json.JSONDecodeError, TypeError):
            continue
    results: list[DiscoveredProperty] = []
    seen: set[str] = set()
    for item in candidates:
        discovered = _candidate_to_property(portal, base_url, item)
        if discovered and discovered.source_url not in seen:
            seen.add(discovered.source_url)
            results.append(discovered)
            if len(results) >= limit:
                return results
    # Fallback conservador: links de anúncio com texto suficiente, sem inferir dados ausentes.
    for href, text in parser.links:
        url = urljoin(base_url, href)
        if url in seen or not _looks_like_listing_url(portal, url) or len(text) < 12:
            continue
        results.append(
            DiscoveredProperty(source=portal, source_url=url, title=text[:300], city="São Paulo")
        )
        seen.add(url)
        if len(results) >= limit:
            break
    return results


def _walk_json(value: Any, candidates: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        action = value.get("potentialAction")
        action_object = action.get("object") if isinstance(action, dict) else None
        if isinstance(action_object, dict) and action_object.get("tourBookingPage"):
            candidates.append(
                {
                    **action_object,
                    "url": action_object["tourBookingPage"],
                    "name": action_object.get("accommodationCategory") or "Imóvel",
                    "price": value.get("price"),
                }
            )
        if _has_listing_shape(value):
            candidates.append(value)
        for child in value.values():
            _walk_json(child, candidates)
    elif isinstance(value, list):
        for child in value:
            _walk_json(child, candidates)


def _has_listing_shape(value: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in value}
    has_url = bool(keys & {"url", "link", "friendlyurl", "detailurl"})
    has_title = bool(keys & {"name", "title", "subject"})
    has_property_data = bool(
        keys
        & {
            "price",
            "offers",
            "area",
            "floorsize",
            "rooms",
            "numberofrooms",
            "bedrooms",
            "properties",
        }
    )
    is_lello_property = "idimovel" in keys and "url" in keys and "tipoimovel" in keys
    return is_lello_property or (has_url and has_title and has_property_data)


def _candidate_to_property(
    portal: str, base_url: str, item: dict[str, Any]
) -> DiscoveredProperty | None:
    source_url = _first(item, "url", "link", "friendlyUrl", "detailUrl")
    title = _first(item, "name", "title", "subject", "titulo")
    if not title and item.get("tipoImovel"):
        title = " em ".join(filter(None, [str(item["tipoImovel"]), _text(item.get("bairro"))]))
    if not source_url or not title:
        return None
    address = item.get("address") if isinstance(item.get("address"), dict) else {}
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    return DiscoveredProperty(
        source=portal,
        source_url=urljoin(base_url, str(source_url)),
        title=str(title)[:300],
        city=str(
            _first(address, "addressLocality", "city")
            or _first(location, "city")
            or item.get("cidade")
            or "São Paulo"
        ),
        neighborhood=_text(
            _first(address, "addressRegion", "neighborhood")
            or _first(location, "neighborhood")
            or item.get("bairro")
        ),
        price=_price(item),
        property_type=_text(_first(item, "propertyType", "type", "category", "tipoImovel")),
        bedrooms=_integer(
            _first(
                item,
                "bedrooms",
                "rooms",
                "numberOfRooms",
                "numberOfBedrooms",
                "quantidadeDormitorios",
            )
            or properties.get("bedrooms")
        ),
        bathrooms=_integer(
            _first(item, "bathrooms", "numberOfBathroomsTotal", "quantidadeBanheiros")
            or properties.get("bathrooms")
        ),
        parking_spaces=_integer(
            _first(item, "parkingSpaces", "garage", "quantidadeVagas")
            or properties.get("parkingSpaces")
        ),
        area=_integer(
            _first(item, "area", "floorSize", "metragemPrincipal") or properties.get("area")
        ),
    )


def _first(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if value.get(key) not in (None, ""):
            return value[key]
    return None


def _price(item: dict[str, Any]) -> str | None:
    value = _first(item, "price", "priceValue", "valorVenda", "valorLocacao")
    if isinstance(value, dict):
        value = _first(value, "value", "price")
    offers = item.get("offers")
    if value is None and isinstance(offers, dict):
        value = _first(offers, "price", "lowPrice")
    return str(value) if value not in (None, "") else None


def _integer(value: Any) -> int | None:
    if isinstance(value, dict):
        value = _first(value, "value", "minValue", "unitText")
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None


def _looks_like_listing_url(portal: str, url: str) -> bool:
    path = urlparse(url).path.lower()
    if portal == "olx":
        return bool(re.search(r"-\d{7,}(?:\?|$)", url))
    return "/imovel/" in path or "/imoveis/" in path
