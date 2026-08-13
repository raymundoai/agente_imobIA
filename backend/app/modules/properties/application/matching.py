from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.leads.domain.entities import LeadDemand
from app.modules.properties.domain.entities import Property, PropertyPurpose

MATCHING_VERSION = "2026-08-13.1"


@dataclass(slots=True)
class PropertyMatch:
    property: Property
    score: int
    matched: list[str] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)


def normalize_search_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def property_offer_price(property_: Property, purpose: str | None) -> Decimal | None:
    if purpose == "rent":
        return property_.rent_price or (
            property_.price if property_.purpose == PropertyPurpose.RENT else None
        )
    if purpose == "buy":
        return property_.sale_price or (
            property_.price if property_.purpose == PropertyPurpose.BUY else None
        )
    return property_.price or property_.sale_price or property_.rent_price


def calculate_property_match(property_: Property, demand: LeadDemand) -> PropertyMatch:
    score = 0
    possible = 0
    matched: list[str] = []
    tradeoffs: list[str] = []

    def criterion(label: str, weight: int, ok: bool | None, failure: str) -> None:
        nonlocal score, possible
        if ok is None:
            return
        possible += weight
        if ok:
            score += weight
            matched.append(label)
        else:
            tradeoffs.append(failure)

    purpose = demand.purpose.value if demand.purpose else None
    criterion(
        "finalidade",
        15,
        property_.purpose in {demand.purpose, PropertyPurpose.BOTH} if demand.purpose else None,
        "finalidade diferente",
    )
    criterion(
        "cidade",
        20,
        normalize_search_text(property_.city) == normalize_search_text(demand.city)
        if demand.city
        else None,
        "outra cidade",
    )
    criterion(
        "tipo",
        10,
        _similar_text(property_.property_type, demand.property_type)
        if demand.property_type
        else None,
        "tipo diferente",
    )
    criterion(
        "bairro",
        15,
        any(_similar_text(property_.neighborhood, item) for item in demand.neighborhoods)
        if demand.neighborhoods
        else None,
        "fora dos bairros preferidos",
    )

    price = property_offer_price(property_, purpose)
    if demand.price_min is not None or demand.price_max is not None:
        price_ok = (
            False
            if price is None
            else (
                (demand.price_min is None or price >= demand.price_min)
                and (demand.price_max is None or price <= demand.price_max)
            )
        )
        criterion("preço", 20, price_ok, "fora da faixa de preço")
    criterion(
        "quartos",
        8,
        None
        if demand.bedrooms is None
        else False
        if property_.bedrooms is None
        else property_.bedrooms >= demand.bedrooms,
        "menos quartos",
    )
    criterion(
        "vagas",
        5,
        None
        if demand.parking_spaces is None
        else False
        if property_.parking_spaces is None
        else property_.parking_spaces >= demand.parking_spaces,
        "menos vagas",
    )
    criterion(
        "área",
        7,
        None
        if demand.min_area is None
        else False
        if property_.area is None
        else property_.area >= demand.min_area,
        "área menor que a desejada",
    )
    return PropertyMatch(
        property=property_,
        score=round(score * 100 / possible) if possible else 100,
        matched=matched,
        tradeoffs=tradeoffs,
    )


def meets_required_constraints(property_: Property, demand: LeadDemand) -> bool:
    """Apply the non-negotiable boundaries before ranking optional preferences."""
    if demand.purpose and property_.purpose not in {demand.purpose, PropertyPurpose.BOTH}:
        return False
    if demand.city and normalize_search_text(property_.city) != normalize_search_text(demand.city):
        return False
    property_state = normalize_search_text(str(property_.address.get("state") or ""))
    demand_state = normalize_search_text(demand.state)
    if demand_state and property_state and property_state != demand_state:
        return False
    price = property_offer_price(
        property_, demand.purpose.value if demand.purpose else None
    )
    if demand.price_min is not None or demand.price_max is not None:
        if price is None:
            return False
        if demand.price_min is not None and price < demand.price_min:
            return False
        if demand.price_max is not None and price > demand.price_max:
            return False
    return True


def _similar_text(left: str | None, right: str | None) -> bool:
    left_normalized = normalize_search_text(left)
    right_normalized = normalize_search_text(right)
    if not left_normalized or not right_normalized:
        return False
    return (
        left_normalized == right_normalized
        or left_normalized in right_normalized
        or right_normalized in left_normalized
    )
