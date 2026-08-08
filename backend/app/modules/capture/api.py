from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.capture.discovery import SUPPORTED_DISCOVERY_PORTALS, PortalDiscoveryAdapter
from app.modules.capture.portals import build_portal_searches
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.properties.adapters.repositories import SqlAlchemyPropertyRepository
from app.modules.properties.api import PropertyResponse
from app.modules.properties.application.use_cases import (
    CapturePropertyUseCase,
    GetCaptureMissionUseCase,
)

router = APIRouter(prefix="/capture", tags=["capture"])


class CapturePropertyRequest(BaseModel):
    demand_id: UUID | None = None
    source: str = Field(min_length=1)
    source_url: AnyHttpUrl | None = None
    title: str = Field(min_length=1)
    city: str = Field(min_length=1)
    neighborhood: str | None = None
    price: Decimal | None = None
    sale_price: Decimal | None = None
    rent_price: Decimal | None = None
    purpose: str | None = None
    property_type: str | None = None
    category: str = "residential"
    status: str = "active"
    listing_code: str | None = None
    description: str | None = None
    bedrooms: int | None = Field(default=None, ge=0)
    suites: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    parking_spaces: int | None = Field(default=None, ge=0)
    area: int | None = Field(default=None, ge=0)
    land_area: int | None = Field(default=None, ge=0)
    address: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    images: list[dict[str, Any]] = Field(default_factory=list)
    advertiser_name: str | None = None
    advertiser_phone: str | None = None


class CaptureMissionResponse(BaseModel):
    demand: dict[str, Any]
    search_filters: dict[str, Any]
    existing_matches: list[dict[str, Any]]
    portal_searches: list[dict[str, Any]]
    federated_sources: list[dict[str, Any]]


class DiscoverMissionRequest(BaseModel):
    portal: str = Field(pattern="^(lello|olx)$")
    limit: int = Field(default=20, ge=1, le=20)


class DiscoverMissionResponse(BaseModel):
    portal: str
    discovered: int
    imported: int
    properties: list[PropertyResponse]


@router.get("/missions/{demand_id}", response_model=CaptureMissionResponse)
def get_mission(
    demand_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> CaptureMissionResponse:
    mission = GetCaptureMissionUseCase(
        SqlAlchemyLeadDemandRepository(session), SqlAlchemyPropertyRepository(session)
    ).execute(principal.tenant_id, demand_id)
    return CaptureMissionResponse(**mission)


@router.post("/missions/{demand_id}/discover", response_model=DiscoverMissionResponse)
def discover_mission_properties(
    demand_id: UUID,
    payload: DiscoverMissionRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> DiscoverMissionResponse:
    leads = SqlAlchemyLeadDemandRepository(session)
    demand = leads.get_by_id(principal.tenant_id, demand_id)
    if demand is None:
        raise HTTPException(status_code=404, detail="Lead demand not found")
    if payload.portal not in SUPPORTED_DISCOVERY_PORTALS:
        raise HTTPException(status_code=400, detail="Portal is not enabled for discovery")
    portal = next(item for item in build_portal_searches(demand) if item.id == payload.portal)
    try:
        discovered = PortalDiscoveryAdapter(container.http_client).discover(
            payload.portal, portal.url, limit=payload.limit
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    use_case = CapturePropertyUseCase(
        leads,
        SqlAlchemyPropertyRepository(session),
        container.event_bus,
    )
    imported = []
    for item in discovered:
        price_fields = (
            {"rent_price": item.price}
            if demand.purpose and demand.purpose.value == "rent"
            else {"sale_price": item.price}
        )
        imported.append(
            use_case.execute(
                principal.tenant_id,
                {
                    "demand_id": demand_id,
                    "source": item.source,
                    "source_url": item.source_url,
                    "title": item.title,
                    "city": item.city,
                    "neighborhood": item.neighborhood,
                    "price": item.price,
                    "purpose": demand.purpose.value if demand.purpose else None,
                    "property_type": item.property_type or demand.property_type,
                    "bedrooms": item.bedrooms,
                    "bathrooms": item.bathrooms,
                    "parking_spaces": item.parking_spaces,
                    "area": item.area,
                    **price_fields,
                },
            )
        )
    return DiscoverMissionResponse(
        portal=payload.portal,
        discovered=len(discovered),
        imported=len(imported),
        properties=[PropertyResponse.from_domain(item) for item in imported],
    )


@router.post(
    "/properties",
    response_model=PropertyResponse,
    status_code=status.HTTP_201_CREATED,
)
def capture_property(
    payload: CapturePropertyRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PropertyResponse:
    property_ = CapturePropertyUseCase(
        SqlAlchemyLeadDemandRepository(session),
        SqlAlchemyPropertyRepository(session),
        container.event_bus,
    ).execute(principal.tenant_id, payload.model_dump())
    return PropertyResponse.from_domain(property_)
