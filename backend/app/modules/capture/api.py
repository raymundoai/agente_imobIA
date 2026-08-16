from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    require_roles,
)
from app.modules.billing_usage.commercial import (
    PROPERTY_SEARCH_AI,
    PROPERTY_SEARCH_STANDARD,
    CommercialEntitlementService,
)
from app.modules.billing_usage.service import (
    CreditLedgerService,
    estimated_chat_charge,
    fixed_credit_charge,
)
from app.modules.capture.connectors import ConnectorRegistry, default_connector_registry
from app.modules.capture.federated import FederatedSearchRepository
from app.modules.capture.models import DemandExternalMatchModel
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.properties.adapters.models import (
    PropertyDemandMatchModel,
    PropertyImageModel,
    PropertyModel,
)
from app.modules.properties.adapters.repositories import SqlAlchemyPropertyRepository
from app.modules.properties.api import PropertyResponse
from app.modules.properties.application.use_cases import (
    CapturePropertyUseCase,
    GetCaptureMissionUseCase,
)
from app.modules.users.domain.entities import UserRole

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


class FederatedSourceResponse(BaseModel):
    id: str
    name: str
    coverage: str
    connector_type: str
    automatic: bool
    premium: bool


class SearchRunRequest(BaseModel):
    demand_id: UUID
    source_ids: list[str] | None = Field(default=None, max_length=20)
    force_refresh: bool = False

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
    source_domain: str
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
    sale_price: Decimal | None
    rent_price: Decimal | None
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
    cache_hit: bool = False
    cache_expires_at: datetime | None = None
    requested_by_user_id: UUID | None = None
    results_has_more: bool = False


class DemandSearchHistoryResponse(BaseModel):
    standard: SearchRunResponse | None
    ai: SearchRunResponse | None


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
            automatic=descriptor.automatic,
            premium=descriptor.premium,
        )
        for descriptor in _connector_registry(container).descriptors()
    ]


@router.get(
    "/demands/{demand_id}/search-history",
    response_model=DemandSearchHistoryResponse,
)
def get_demand_search_history(
    demand_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> DemandSearchHistoryResponse:
    demand = SqlAlchemyLeadDemandRepository(session).get_by_id(principal.tenant_id, demand_id)
    if demand is None:
        raise HTTPException(status_code=404, detail="Lead demand not found")
    registry = _connector_registry(container)
    repository = FederatedSearchRepository(session)
    available = registry.available_for(demand)
    standard_source_ids = sorted(
        item.id for item in available if item.automatic and not item.premium
    )
    ai_source_ids = [item.id for item in available if item.id == "web_discovery" and item.premium]
    standard = (
        repository.latest_compatible_run(
            principal.tenant_id,
            demand,
            standard_source_ids,
            catalog_version=registry.catalog_version(standard_source_ids),
        )
        if standard_source_ids
        else None
    )
    ai = (
        repository.latest_compatible_run(
            principal.tenant_id,
            demand,
            ai_source_ids,
            catalog_version=registry.catalog_version(ai_source_ids),
        )
        if ai_source_ids
        else None
    )
    return DemandSearchHistoryResponse(
        standard=(
            _search_run_response(
                session,
                principal.tenant_id,
                standard.id,
                registry,
                cache_hit=True,
            )
            if standard
            else None
        ),
        ai=(
            _search_run_response(
                session,
                principal.tenant_id,
                ai.id,
                registry,
                cache_hit=True,
            )
            if ai
            else None
        ),
    )


@router.post(
    "/search-runs",
    response_model=SearchRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_search_run(
    payload: SearchRunRequest,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> SearchRunResponse:
    demand = SqlAlchemyLeadDemandRepository(session).get_by_id(
        principal.tenant_id, payload.demand_id
    )
    if demand is None:
        raise HTTPException(status_code=404, detail="Lead demand not found")
    if demand.status.value == "closed":
        raise HTTPException(status_code=409, detail="Reabra a demanda antes de pesquisar")
    if not demand.city or not demand.purpose:
        raise HTTPException(
            status_code=422,
            detail="Informe finalidade e cidade antes de iniciar a busca externa",
        )
    registry = _connector_registry(container)
    available_descriptors = registry.available_for(demand)
    available = {item.id for item in available_descriptors}
    requested = (
        payload.source_ids
        if payload.source_ids is not None
        else sorted(item.id for item in available_descriptors if item.automatic)
    )
    unknown = set(requested) - available
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Fontes indisponíveis para esta demanda: {', '.join(sorted(unknown))}",
        )
    selected_descriptors = [registry.get(source_id).descriptor for source_id in requested]
    if any(item.premium for item in selected_descriptors) and len(selected_descriptors) != 1:
        raise HTTPException(
            status_code=422,
            detail="Fontes premium devem ser executadas em uma busca separada",
        )
    if not requested:
        raise HTTPException(status_code=422, detail="Nenhuma fonte disponível para esta região")
    repository = FederatedSearchRepository(session)
    catalog_version = registry.catalog_version(requested)
    run = (
        None
        if payload.force_refresh
        else repository.find_reusable_run(
            principal.tenant_id,
            demand,
            requested,
            catalog_version=catalog_version,
        )
    )
    cache_hit = run is not None
    if run is None:
        run_id = uuid4()
        premium = any(item.premium for item in selected_descriptors)
        billing_key = f"capture-search:{run_id}"
        commercial_billing_key = f"commercial:{billing_key}"
        billing_model = (
            container.settings.capture_web_discovery_model if premium else "federated-standard-v1"
        )
        estimate = (
            estimated_chat_charge(billing_model)
            if premium
            else fixed_credit_charge(container.settings.capture_standard_search_credits)
        )
        try:
            CommercialEntitlementService(session).reserve(
                principal.tenant_id,
                resource=PROPERTY_SEARCH_AI if premium else PROPERTY_SEARCH_STANDARD,
                idempotency_key=commercial_billing_key,
                reference_id=run_id,
                ttl_seconds=max(container.settings.capture_job_stale_seconds * 5, 900),
                extra={"premium": premium, "source_ids": requested},
            )
            CreditLedgerService(session).reserve(
                principal.tenant_id,
                resource="property_search_ai" if premium else "property_search_standard",
                model=billing_model,
                estimate=estimate,
                idempotency_key=billing_key,
                reference_id=run_id,
                ttl_seconds=max(container.settings.capture_job_stale_seconds * 5, 900),
            )
            run = repository.create_run(
                principal.tenant_id,
                demand,
                requested,
                run_id=run_id,
                requested_by_user_id=principal.user_id,
                catalog_version=catalog_version,
                cache_ttl_seconds=container.settings.capture_search_cache_ttl_seconds,
                force_refresh=payload.force_refresh,
                billing_reservation_key=billing_key,
                max_attempts=container.settings.capture_job_max_attempts,
            )
        except IntegrityError:
            session.rollback()
            CreditLedgerService(session).release_reservation(principal.tenant_id, billing_key)
            CommercialEntitlementService(session).release(
                principal.tenant_id, commercial_billing_key
            )
            run = repository.find_reusable_run(
                principal.tenant_id,
                demand,
                requested,
                catalog_version=catalog_version,
            )
            if run is None:
                raise
            cache_hit = True
        except Exception:
            session.rollback()
            CreditLedgerService(session).release_reservation(principal.tenant_id, billing_key)
            CommercialEntitlementService(session).release(
                principal.tenant_id, commercial_billing_key
            )
            raise
    return _search_run_response(
        session,
        principal.tenant_id,
        run.id,
        registry,
        cache_hit=cache_hit,
    )


@router.get("/search-runs/{run_id}", response_model=SearchRunResponse)
def get_search_run(
    run_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
    include_results: bool = Query(default=True),
) -> SearchRunResponse:
    return _search_run_response(
        session,
        principal.tenant_id,
        run_id,
        _connector_registry(container),
        include_results=include_results,
    )


@router.get(
    "/search-runs/{run_id}/results",
    response_model=list[ExternalSearchResultResponse],
)
def list_search_run_results(
    run_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    fit_min: int | None = Query(default=None, ge=0, le=100),
    fit_max: int | None = Query(default=None, ge=0, le=100),
    source_id: str | None = None,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> list[ExternalSearchResultResponse]:
    repository = FederatedSearchRepository(session)
    if repository.get_run(principal.tenant_id, run_id) is None:
        raise HTTPException(status_code=404, detail="Search run not found")
    descriptors = {item.id: item for item in _connector_registry(container).descriptors()}
    return [
        ExternalSearchResultResponse(
            **item,
            source_name=(
                descriptors[str(item["source_id"])].name
                if str(item["source_id"]) in descriptors
                else str(item["source_id"])
            ),
        )
        for item in repository.list_results(
            principal.tenant_id,
            run_id,
            limit=limit,
            offset=offset,
            fit_min=fit_min,
            fit_max=fit_max,
            source_id=source_id,
        )
    ]


@router.post("/search-runs/{run_id}/cancel", response_model=SearchRunResponse)
def cancel_search_run(
    run_id: UUID,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> SearchRunResponse:
    run = FederatedSearchRepository(session).cancel_run(principal.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Search run not found")
    if run.billing_reservation_key:
        ledger = CreditLedgerService(session)
        if (
            ledger.reservation_status(principal.tenant_id, run.billing_reservation_key)
            == "reserved"
        ):
            ledger.release_reservation(principal.tenant_id, run.billing_reservation_key)
        CommercialEntitlementService(session).release(
            principal.tenant_id, f"commercial:{run.billing_reservation_key}"
        )
    return _search_run_response(
        session, principal.tenant_id, run.id, _connector_registry(container)
    )


@router.post(
    "/search-runs/{run_id}/sources/{source_id}/retry",
    response_model=SearchRunResponse,
)
def retry_search_source(
    run_id: UUID,
    source_id: str,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> SearchRunResponse:
    if source_id == "web_discovery":
        raise HTTPException(
            status_code=409,
            detail="Use Atualizar descoberta com IA para repetir a fonte premium",
        )
    try:
        run = FederatedSearchRepository(session).retry_source(
            principal.tenant_id, run_id, source_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="Search source not found")
    return _search_run_response(
        session, principal.tenant_id, run.id, _connector_registry(container)
    )


@router.post(
    "/search-runs/{run_id}/results/{listing_id}/save",
    response_model=PropertyResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_search_result(
    run_id: UUID,
    listing_id: UUID,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PropertyResponse:
    repository = FederatedSearchRepository(session)
    result = repository.get_result_for_capture(principal.tenant_id, run_id, listing_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Search result not found")
    demand_id, capture_data = result
    property_ = CapturePropertyUseCase(
        SqlAlchemyLeadDemandRepository(session),
        SqlAlchemyPropertyRepository(session),
        container.event_bus,
    ).execute(
        principal.tenant_id,
        {"demand_id": demand_id, **capture_data},
        commit=False,
    )
    external_image_url = next(
        (
            str(item.get("url"))
            for item in capture_data.get("images", [])
            if isinstance(item, dict) and item.get("url")
        ),
        None,
    )
    has_media = session.scalar(
        select(func.count(PropertyImageModel.id)).where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_.id,
        )
    )
    if external_image_url and not has_media:
        session.add(
            PropertyImageModel(
                id=uuid4(),
                tenant_id=principal.tenant_id,
                property_id=property_.id,
                legacy_url=external_image_url,
                legacy_metadata={"external_capture": True},
                original_name="Imagem do anúncio externo",
                original_content_type="image/jpeg",
                original_size=0,
                status="ready",
                is_primary=True,
                sort_order=0,
            )
        )
        session.flush()
    if not repository.mark_result_saved(
        principal.tenant_id,
        run_id,
        listing_id,
        property_id=property_.id,
        commit=False,
    ):
        session.rollback()
        raise HTTPException(status_code=409, detail="Search result could not be saved")
    session.commit()
    return PropertyResponse.from_domain(property_)


@router.delete(
    "/search-runs/{run_id}/results/{listing_id}/save",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unsave_search_result(
    run_id: UUID,
    listing_id: UUID,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
) -> None:
    repository = FederatedSearchRepository(session)
    result = repository.mark_result_unsaved(principal.tenant_id, run_id, listing_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Search result not found")
    demand_id, property_id = result
    if property_id is not None:
        link = session.scalar(
            select(PropertyDemandMatchModel).where(
                PropertyDemandMatchModel.tenant_id == principal.tenant_id,
                PropertyDemandMatchModel.demand_id == demand_id,
                PropertyDemandMatchModel.property_id == property_id,
            )
        )
        if link is not None:
            session.delete(link)
            session.flush()
        remaining = session.scalar(
            select(func.count(PropertyDemandMatchModel.id)).where(
                PropertyDemandMatchModel.tenant_id == principal.tenant_id,
                PropertyDemandMatchModel.property_id == property_id,
            )
        )
        property_model = session.scalar(
            select(PropertyModel).where(
                PropertyModel.tenant_id == principal.tenant_id,
                PropertyModel.id == property_id,
            )
        )
        if not remaining and property_model is not None and property_model.source != "manual":
            session.delete(property_model)
    session.commit()


@router.post(
    "/missions/{demand_id}/discover",
    deprecated=True,
    status_code=status.HTTP_410_GONE,
)
def discover_mission_properties(
    demand_id: UUID,
    _payload: DiscoverMissionRequest,
    _: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
) -> None:
    """Keep the old route discoverable without bypassing the federated workflow."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            f"A descoberta legada da demanda {demand_id} foi substituída por "
            "POST /capture/search-runs"
        ),
    )


@router.post(
    "/properties",
    response_model=PropertyResponse,
    status_code=status.HTTP_201_CREATED,
)
def capture_property(
    payload: CapturePropertyRequest,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PropertyResponse:
    property_ = CapturePropertyUseCase(
        SqlAlchemyLeadDemandRepository(session),
        SqlAlchemyPropertyRepository(session),
        container.event_bus,
    ).execute(principal.tenant_id, payload.model_dump())
    return PropertyResponse.from_domain(property_)


@router.delete(
    "/demands/{demand_id}/properties/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_saved_property(
    demand_id: UUID,
    property_id: UUID,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
) -> None:
    demand = SqlAlchemyLeadDemandRepository(session).get_by_id(principal.tenant_id, demand_id)
    property_model = session.scalar(
        select(PropertyModel).where(
            PropertyModel.tenant_id == principal.tenant_id,
            PropertyModel.id == property_id,
            PropertyModel.source != "manual",
        )
    )
    link = session.scalar(
        select(PropertyDemandMatchModel).where(
            PropertyDemandMatchModel.tenant_id == principal.tenant_id,
            PropertyDemandMatchModel.demand_id == demand_id,
            PropertyDemandMatchModel.property_id == property_id,
        )
    )
    if demand is None or property_model is None or link is None:
        raise HTTPException(status_code=404, detail="Saved property not found")
    match = session.scalar(
        select(DemandExternalMatchModel).where(
            DemandExternalMatchModel.tenant_id == principal.tenant_id,
            DemandExternalMatchModel.demand_id == demand_id,
            DemandExternalMatchModel.saved_property_id == property_id,
        )
    )
    if match is not None:
        match.review_status = "new"
        match.saved_property_id = None
    session.delete(link)
    session.flush()
    remaining = session.scalar(
        select(func.count(PropertyDemandMatchModel.id)).where(
            PropertyDemandMatchModel.tenant_id == principal.tenant_id,
            PropertyDemandMatchModel.property_id == property_id,
        )
    )
    if not remaining:
        session.delete(property_model)
    session.commit()


def _search_run_response(
    session: Session,
    tenant_id: UUID,
    run_id: UUID,
    registry: ConnectorRegistry,
    *,
    cache_hit: bool = False,
    include_results: bool = True,
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
    for item in repository.list_results(tenant_id, run_id, limit=60) if include_results else []:
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
        cache_hit=cache_hit,
        cache_expires_at=run.cache_expires_at,
        requested_by_user_id=run.requested_by_user_id,
        results_has_more=include_results and run.result_count > len(results),
    )


def _connector_registry(container: Container) -> ConnectorRegistry:
    settings = container.settings
    return default_connector_registry(
        container.capture_http_client,
        web_discovery_enabled=settings.capture_web_discovery_enabled,
        openai_api_key=(
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        ),
        web_discovery_model=settings.capture_web_discovery_model,
        web_discovery_max_results=settings.capture_web_discovery_max_results,
        web_discovery_max_output_tokens=settings.capture_web_discovery_max_output_tokens,
    )
