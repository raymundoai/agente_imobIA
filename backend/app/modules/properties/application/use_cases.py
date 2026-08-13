from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.modules.leads.domain.entities import LeadDemand, LeadPurpose
from app.modules.leads.ports.repositories import LeadDemandRepositoryPort
from app.modules.properties.application.matching import (
    calculate_property_match,
    property_offer_price,
)
from app.modules.properties.domain.entities import Property, PropertyPurpose
from app.modules.properties.ports.repositories import PropertyRepositoryPort
from app.shared.errors.exceptions import NotFoundError
from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort


class CapturePropertyUseCase:
    def __init__(
        self,
        leads: LeadDemandRepositoryPort,
        properties: PropertyRepositoryPort,
        events: EventBusPort,
    ) -> None:
        self._leads = leads
        self._properties = properties
        self._events = events

    def execute(
        self,
        tenant_id: UUID,
        data: dict[str, Any],
        *,
        commit: bool = True,
    ) -> Property:
        demand_id = _uuid_or_none(data.get("demand_id"))
        if demand_id and self._leads.get_by_id(tenant_id, demand_id) is None:
            raise NotFoundError("Lead demand not found")
        property_ = normalize_property(tenant_id, data)
        saved = (
            self._properties.upsert_captured(tenant_id, property_, demand_id)
            if commit
            else self._properties.upsert_captured(
                tenant_id, property_, demand_id, commit=False
            )
        )
        self._events.publish(
            DomainEvent(
                name="PropertyCaptured",
                tenant_id=tenant_id,
                payload={
                    "property_id": str(saved.id),
                    "demand_id": str(demand_id) if demand_id else None,
                },
            )
        )
        return saved


class GetCaptureMissionUseCase:
    def __init__(self, leads: LeadDemandRepositoryPort, properties: PropertyRepositoryPort) -> None:
        self._leads = leads
        self._properties = properties

    def execute(self, tenant_id: UUID, demand_id: UUID) -> dict[str, Any]:
        demand = self._leads.get_by_id(tenant_id, demand_id)
        if demand is None:
            raise NotFoundError("Lead demand not found")
        existing = [
            item
            for item in self._properties.list(tenant_id, demand_id=demand_id, limit=50)
            if item.source != "manual"
        ][:20]
        matches = [calculate_property_match(item, demand) for item in existing]
        from app.modules.capture.portals import build_portal_searches
        from app.modules.capture.sources import build_federated_sources

        return {
            "demand": _demand_payload(demand),
            "search_filters": {
                "city": demand.city,
                "state": demand.state,
                "purpose": demand.purpose.value if demand.purpose else None,
                "property_type": demand.property_type,
                "neighborhoods": demand.neighborhoods,
                "price_min": str(demand.price_min) if demand.price_min is not None else None,
                "price_max": str(demand.price_max) if demand.price_max is not None else None,
                "bedrooms": demand.bedrooms,
                "parking_spaces": demand.parking_spaces,
                "min_area": demand.min_area,
            },
            "existing_matches": [
                {
                    "id": str(match.property.id),
                    "title": match.property.title,
                    "source_url": match.property.source_url,
                    "price": str(
                        property_offer_price(
                            match.property,
                            demand.purpose.value if demand.purpose else None,
                        )
                    )
                    if property_offer_price(
                        match.property,
                        demand.purpose.value if demand.purpose else None,
                    ) is not None
                    else None,
                    "score": match.score,
                    "matched": match.matched,
                    "tradeoffs": match.tradeoffs,
                }
                for match in matches
            ],
            "portal_searches": [
                {
                    "id": portal.id,
                    "name": portal.name,
                    "url": portal.url,
                    "applied_filters": portal.applied_filters,
                    "pending_filters": portal.pending_filters,
                    "discovery_mode": portal.discovery_mode,
                    "status_message": portal.status_message,
                }
                for portal in build_portal_searches(demand)
            ],
            "federated_sources": build_federated_sources(demand),
        }


class ListPropertiesUseCase:
    def __init__(self, properties: PropertyRepositoryPort) -> None:
        self._properties = properties

    def execute(
        self,
        tenant_id: UUID,
        *,
        demand_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Property]:
        return self._properties.list(tenant_id, demand_id=demand_id, limit=limit, offset=offset)


def normalize_property(tenant_id: UUID, data: dict[str, Any]) -> Property:
    source_url = _optional_text(data.get("source_url"))
    title = _text(data.get("title")) or "Imóvel sem título"
    city = _text(data.get("city"))
    neighborhood = _optional_text(data.get("neighborhood"))
    purpose = _purpose(data.get("purpose"))
    legacy_price = _decimal_or_none(data.get("price"))
    sale_price = _decimal_or_none(data.get("sale_price"))
    rent_price = _decimal_or_none(data.get("rent_price"))
    if purpose == PropertyPurpose.BUY and sale_price is None:
        sale_price = legacy_price
    if purpose == PropertyPurpose.RENT and rent_price is None:
        rent_price = legacy_price
    property_ = Property(
        tenant_id=tenant_id,
        source=_text(data.get("source")) or "unknown",
        source_url=source_url,
        title=title,
        city=city,
        neighborhood=neighborhood,
        price=legacy_price or sale_price or rent_price,
        sale_price=sale_price,
        rent_price=rent_price,
        purpose=purpose,
        property_type=_optional_text(data.get("property_type")),
        category=_optional_text(data.get("category")) or "residential",
        status=_optional_text(data.get("status")) or "active",
        listing_code=_optional_text(data.get("listing_code")),
        description=_optional_text(data.get("description")),
        bedrooms=_int_or_none(data.get("bedrooms")),
        suites=_int_or_none(data.get("suites")),
        bathrooms=_int_or_none(data.get("bathrooms")),
        parking_spaces=_int_or_none(data.get("parking_spaces")),
        area=_int_or_none(data.get("area")),
        land_area=_int_or_none(data.get("land_area")),
        address=data.get("address") if isinstance(data.get("address"), dict) else {},
        details=data.get("details") if isinstance(data.get("details"), dict) else {},
        images=data.get("images") if isinstance(data.get("images"), list) else [],
        advertiser_name=_optional_text(data.get("advertiser_name")),
        advertiser_phone=_optional_text(data.get("advertiser_phone")),
        via_extension=True,
        content_hash=_content_hash(data),
        updated_at=datetime.now(UTC),
    )
    return property_


def _content_hash(data: dict[str, Any]) -> str:
    if data.get("source_url"):
        return hashlib.sha256(str(data["source_url"]).strip().lower().encode()).hexdigest()
    key = "|".join(
        [
            _text(data.get("source")).lower(),
            _text(data.get("title")).lower(),
            _text(data.get("city")).lower(),
            _text(data.get("neighborhood")).lower(),
            str(_decimal_or_none(data.get("price")) or ""),
            str(_int_or_none(data.get("bedrooms")) or ""),
            str(_int_or_none(data.get("area")) or ""),
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()


def _demand_payload(demand: LeadDemand) -> dict[str, Any]:
    return {
        "id": str(demand.id),
        "lead_name": demand.lead_name,
        "phone": demand.phone,
        "purpose": demand.purpose.value if demand.purpose else None,
        "property_type": demand.property_type,
        "city": demand.city,
        "state": demand.state,
        "neighborhoods": demand.neighborhoods,
        "price_min": str(demand.price_min) if demand.price_min is not None else None,
        "price_max": str(demand.price_max) if demand.price_max is not None else None,
        "bedrooms": demand.bedrooms,
        "parking_spaces": demand.parking_spaces,
        "min_area": demand.min_area,
        "notes": demand.notes,
        "status": demand.status.value,
    }


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _purpose(value: Any) -> PropertyPurpose | None:
    if value is None:
        return None
    value_str = str(value)
    if value_str == LeadPurpose.BUY.value:
        return PropertyPurpose.BUY
    if value_str == LeadPurpose.RENT.value:
        return PropertyPurpose.RENT
    if value_str == PropertyPurpose.BOTH.value:
        return PropertyPurpose.BOTH
    return None


def _uuid_or_none(value: Any) -> UUID | None:
    if not value:
        return None
    return UUID(str(value))
