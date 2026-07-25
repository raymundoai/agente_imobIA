from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.leads.domain.entities import LeadDemand
from app.modules.properties.domain.entities import Property, PropertyPurpose


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
            None
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
        property_.bedrooms >= demand.bedrooms
        if property_.bedrooms is not None and demand.bedrooms is not None
        else None,
        "menos quartos",
    )
    criterion(
        "vagas",
        5,
        property_.parking_spaces >= demand.parking_spaces
        if property_.parking_spaces is not None and demand.parking_spaces is not None
        else None,
        "menos vagas",
    )
    criterion(
        "área",
        7,
        property_.area >= demand.min_area
        if property_.area is not None and demand.min_area is not None
        else None,
        "área menor que a desejada",
    )
    return PropertyMatch(
        property=property_,
        score=round(score * 100 / possible) if possible else 100,
        matched=matched,
        tradeoffs=tradeoffs,
    )


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
