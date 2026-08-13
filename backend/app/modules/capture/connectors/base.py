from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx

from app.modules.leads.domain.entities import LeadDemand


class ConnectorError(RuntimeError):
    error_code = "connector_error"
    retryable = True


class SourceBlockedError(ConnectorError):
    error_code = "source_blocked"
    retryable = False


class SourceShapeError(ConnectorError):
    error_code = "source_shape_changed"
    retryable = False


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    id: str
    name: str
    coverage: str
    connector_type: str = "http"
    automatic: bool = True
    premium: bool = False


@dataclass(slots=True)
class ExternalListingRecord:
    source_id: str
    source_listing_id: str
    canonical_url: str
    title: str
    city: str
    state: str | None = None
    neighborhood: str | None = None
    description: str | None = None
    purpose: str | None = None
    property_type: str | None = None
    price: Decimal | None = None
    sale_price: Decimal | None = None
    rent_price: Decimal | None = None
    condominium_fee: Decimal | None = None
    property_tax: Decimal | None = None
    bedrooms: int | None = None
    suites: int | None = None
    bathrooms: int | None = None
    parking_spaces: int | None = None
    area: int | None = None
    land_area: int | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    address: dict[str, Any] = field(default_factory=dict)
    primary_image_url: str | None = None
    advertiser_name: str | None = None
    advertiser_phone: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
    extraction_confidence: int = 80

    def content_hash(self) -> str:
        material = {
            key: value
            for key, value in asdict(self).items()
            if key not in {"raw_data", "extraction_confidence"}
        }
        return hashlib.sha256(
            json.dumps(material, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()

    def completeness_score(self) -> int:
        values = (
            self.title,
            self.city,
            self.neighborhood,
            self.purpose,
            self.property_type,
            self.price,
            self.bedrooms,
            self.bathrooms,
            self.parking_spaces,
            self.area,
            self.primary_image_url,
        )
        return round(sum(value not in (None, "") for value in values) * 100 / len(values))


@dataclass(frozen=True, slots=True)
class ConnectorBatch:
    source: SourceDescriptor
    parser_version: str
    request_url: str
    records: list[ExternalListingRecord]
    metadata: dict[str, Any] = field(default_factory=dict)


class PortalConnector(ABC):
    descriptor: SourceDescriptor
    parser_version = "1"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def supports(self, demand: LeadDemand) -> bool:
        return bool(demand.city)

    @abstractmethod
    def search(self, demand: LeadDemand, *, limit: int = 24) -> ConnectorBatch:
        raise NotImplementedError

    def get_public(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        request_headers = {
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
            ),
        }
        request_headers.update(headers or {})
        response = self.client.get(
            url,
            headers=request_headers,
            follow_redirects=True,
        )
        challenge = response.text[:50_000].casefold()
        if response.status_code in {401, 403, 429} or any(
            marker in challenge
            for marker in (
                "attention required! | cloudflare",
                "just a moment...",
                "cf-chl-",
                "captcha-delivery.com",
            )
        ):
            raise SourceBlockedError(f"{self.descriptor.name} bloqueou a leitura automatizada")
        response.raise_for_status()
        return response

    def post_public(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_headers = {
            "Accept": "application/json",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
            ),
        }
        request_headers.update(headers or {})
        response = self.client.post(
            url,
            headers=request_headers,
            json=json,
            follow_redirects=True,
        )
        challenge = response.text[:50_000].casefold()
        if response.status_code in {401, 403, 429} or any(
            marker in challenge
            for marker in (
                "attention required! | cloudflare",
                "just a moment...",
                "cf-chl-",
                "captcha-delivery.com",
            )
        ):
            raise SourceBlockedError(f"{self.descriptor.name} bloqueou a leitura automatizada")
        response.raise_for_status()
        return response


def slug(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")


def infer_state(city: str | None, explicit_state: str | None = None) -> str | None:
    if explicit_state and len(explicit_state.strip()) == 2:
        return explicit_state.strip().upper()
    by_city = {
        "sao paulo": "SP",
        "americana": "SP",
        "barueri": "SP",
        "bauru": "SP",
        "campinas": "SP",
        "carapicuiba": "SP",
        "cotia": "SP",
        "diadema": "SP",
        "guaruja": "SP",
        "guarulhos": "SP",
        "jundiai": "SP",
        "mogi das cruzes": "SP",
        "osasco": "SP",
        "piracicaba": "SP",
        "ribeirao preto": "SP",
        "santo andre": "SP",
        "santos": "SP",
        "sao bernardo do campo": "SP",
        "sao caetano do sul": "SP",
        "sao jose do rio preto": "SP",
        "sao jose dos campos": "SP",
        "sorocaba": "SP",
        "sumare": "SP",
        "taubate": "SP",
        "alvorada": "RS",
        "cachoeirinha": "RS",
        "campo bom": "RS",
        "bento goncalves": "RS",
        "canela": "RS",
        "capao da canoa": "RS",
        "caxias do sul": "RS",
        "porto alegre": "RS",
        "canoas": "RS",
        "dois irmaos": "RS",
        "eldorado do sul": "RS",
        "estancia velha": "RS",
        "esteio": "RS",
        "gramado": "RS",
        "gravatai": "RS",
        "guaiba": "RS",
        "igrejinha": "RS",
        "ivoti": "RS",
        "lajeado": "RS",
        "novo hamburgo": "RS",
        "osorio": "RS",
        "passo fundo": "RS",
        "pelotas": "RS",
        "rio grande": "RS",
        "santa cruz do sul": "RS",
        "santa maria": "RS",
        "sapiranga": "RS",
        "sapucaia do sul": "RS",
        "sao leopoldo": "RS",
        "taquara": "RS",
        "torres": "RS",
        "tramandai": "RS",
        "viamao": "RS",
        "salvador": "BA",
        "lauro de freitas": "BA",
        "mata de sao joao": "BA",
        "camacari": "BA",
        "simoes filho": "BA",
        "rio de janeiro": "RJ",
    }
    return by_city.get(slug(city).replace("-", " "))


def decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    raw = re.sub(r"[^0-9,.-]", "", str(value))
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1 or (raw.count(".") == 1 and len(raw.rsplit(".", 1)[1]) == 3):
        raw = raw.replace(".", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def integer_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        value = value.get("value") or value.get("minValue") or value.get("unitText")
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def listing_id_from_url(url: str) -> str:
    path = urlparse(url).path
    match = re.search(r"(?:/|^)(?:id-)?([A-Z]{2,6}\d{3,}|\d{5,})(?:/|$)", path, re.I)
    if match:
        return match.group(1)
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def requested_purpose(demand: LeadDemand) -> str | None:
    return demand.purpose.value if demand.purpose else None


def available_purpose(
    sale_price: Decimal | None,
    rent_price: Decimal | None,
    fallback: str | None = None,
) -> str | None:
    if sale_price is not None and rent_price is not None:
        return "both"
    if rent_price is not None:
        return "rent"
    if sale_price is not None:
        return "buy"
    return fallback
