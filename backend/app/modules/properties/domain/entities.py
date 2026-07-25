from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class PropertyPurpose(StrEnum):
    BUY = "buy"
    RENT = "rent"
    BOTH = "both"


@dataclass(slots=True)
class Property:
    tenant_id: UUID
    source: str
    title: str
    city: str
    id: UUID = field(default_factory=uuid4)
    source_url: str | None = None
    neighborhood: str | None = None
    price: Decimal | None = None
    sale_price: Decimal | None = None
    rent_price: Decimal | None = None
    purpose: PropertyPurpose | None = None
    property_type: str | None = None
    category: str = "residential"
    status: str = "active"
    listing_code: str | None = None
    description: str | None = None
    bedrooms: int | None = None
    suites: int | None = None
    bathrooms: int | None = None
    parking_spaces: int | None = None
    area: int | None = None
    land_area: int | None = None
    address: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    images: list[dict[str, Any]] = field(default_factory=list)
    advertiser_name: str | None = None
    advertiser_phone: str | None = None
    via_extension: bool = False
    duplicate_group_id: UUID | None = None
    content_hash: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class PropertyDemandMatch:
    tenant_id: UUID
    property_id: UUID
    demand_id: UUID
    match_score: int = 100
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
