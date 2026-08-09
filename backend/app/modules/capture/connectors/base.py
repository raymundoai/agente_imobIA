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

    def get_public(self, url: str) -> httpx.Response:
        response = self.client.get(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/json",
                "Accept-Language": "pt-BR,pt;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
                ),
            },
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


def infer_state(city: str | None) -> str | None:
    by_city = {
        "sao paulo": "SP",
        "porto alegre": "RS",
        "canoas": "RS",
        "gravatai": "RS",
        "novo hamburgo": "RS",
        "sao leopoldo": "RS",
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
