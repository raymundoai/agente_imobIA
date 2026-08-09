from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.capture.connectors import ConnectorRegistry, default_connector_registry
from app.modules.capture.discovery import SUPPORTED_DISCOVERY_PORTALS, PortalDiscoveryAdapter
from app.modules.capture.federated import FederatedSearchRepository
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


class FederatedSourceResponse(BaseModel):
    id: str
    name: str
    coverage: str
    connector_type: str


class SearchRunRequest(BaseModel):
    demand_id: UUID
    source_ids: list[str] | None = Field(default=None, max_length=12)

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("source_ids must be unique")
        return value


class SearchRunSourceResponse(BaseModel):
    source_id: str
    source_name: str
    status: str
    discovered_count: int
    imported_count: int
    error_code: str | None
    error: str | None
    parser_version: str | None


class ExternalSearchResultResponse(BaseModel):
    id: UUID
    source_id: str
    source_name: str
    source_listing_id: str
    canonical_url: str
    title: str
    description: str | None
    purpose: str | None
    property_type: str | None
    state: str | None
    city: str
    neighborhood: str | None
    price: Decimal | None
    bedrooms: int | None
    bathrooms: int | None
    parking_spaces: int | None
    area: int | None
    primary_image_url: str | None
    advertiser_name: str | None
    fit_score: int
    confidence_score: int
    matched: list[str]
    tradeoffs: list[str]
    review_status: str
    last_seen_at: datetime


class SearchRunResponse(BaseModel):
    id: UUID
    demand_id: UUID
    status: str
    filters: dict[str, Any]
    source_count: int
    completed_source_count: int
    result_count: int
    error: str | None
    sources: list[SearchRunSourceResponse]
    results: list[ExternalSearchResultResponse]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


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


@router.get("/sources", response_model=list[FederatedSourceResponse])
def list_federated_sources(
    _: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
) -> list[FederatedSourceResponse]:
    return [
        FederatedSourceResponse(
            id=descriptor.id,
            name=descriptor.name,
            coverage=descriptor.coverage,
            connector_type=descriptor.connector_type,
        )
        for descriptor in default_connector_registry(container.http_client).descriptors()
    ]


@router.post(
    "/search-runs",
    response_model=SearchRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_search_run(
    payload: SearchRunRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> SearchRunResponse:
    demand = SqlAlchemyLeadDemandRepository(session).get_by_id(
        principal.tenant_id, payload.demand_id
    )
    if demand is None:
        raise HTTPException(status_code=404, detail="Lead demand not found")
    if not demand.city or not demand.purpose:
        raise HTTPException(
            status_code=422,
            detail="Informe finalidade e cidade antes de iniciar a busca externa",
        )
    registry = default_connector_registry(container.http_client)
    available = {item.id for item in registry.available_for(demand)}
    requested = payload.source_ids or sorted(available)
    unknown = set(requested) - available
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Fontes indisponíveis para esta demanda: {', '.join(sorted(unknown))}",
        )
    if not requested:
        raise HTTPException(status_code=422, detail="Nenhuma fonte disponível para esta região")
    run = FederatedSearchRepository(session).create_run(
        principal.tenant_id,
        demand,
        requested,
        max_attempts=container.settings.capture_job_max_attempts,
    )
    return _search_run_response(session, principal.tenant_id, run.id, registry)


@router.get("/search-runs/{run_id}", response_model=SearchRunResponse)
def get_search_run(
    run_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> SearchRunResponse:
    return _search_run_response(
        session,
        principal.tenant_id,
        run_id,
        default_connector_registry(container.http_client),
    )


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


def _search_run_response(
    session: Session,
    tenant_id: UUID,
    run_id: UUID,
    registry: ConnectorRegistry,
) -> SearchRunResponse:
    repository = FederatedSearchRepository(session)
    run = repository.get_run(tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Search run not found")
    descriptors = {item.id: item for item in registry.descriptors()}
    sources = [
        SearchRunSourceResponse(
            source_id=item.source_id,
            source_name=(
                descriptors[item.source_id].name
                if item.source_id in descriptors
                else item.source_id
            ),
            status=item.status,
            discovered_count=item.discovered_count,
            imported_count=item.imported_count,
            error_code=item.error_code,
            error=item.error,
            parser_version=item.parser_version,
        )
        for item in repository.list_run_sources(tenant_id, run_id)
    ]
    results = []
    for item in repository.list_results(tenant_id, run_id):
        descriptor = descriptors.get(str(item["source_id"]))
        results.append(
            ExternalSearchResultResponse(
                **item,
                source_name=descriptor.name if descriptor else str(item["source_id"]),
            )
        )
    return SearchRunResponse(
        id=run.id,
        demand_id=run.demand_id,
        status=run.status,
        filters=run.filters,
        source_count=run.source_count,
        completed_source_count=run.completed_source_count,
        result_count=run.result_count,
        error=run.error,
        sources=sources,
        results=results,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )
