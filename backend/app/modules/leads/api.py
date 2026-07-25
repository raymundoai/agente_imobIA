from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.domain.entities import LeadDemand, LeadDemandStatus, LeadPurpose
from app.shared.errors.exceptions import NotFoundError

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadDemandRequest(BaseModel):
    lead_name: str = Field(min_length=1)
    phone: str = Field(min_length=3)
    purpose: LeadPurpose | None = None
    property_type: str | None = None
    city: str | None = None
    neighborhoods: list[str] = Field(default_factory=list)
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    bedrooms: int | None = Field(default=None, ge=0)
    parking_spaces: int | None = Field(default=None, ge=0)
    min_area: int | None = Field(default=None, ge=0)
    notes: str | None = None
    status: LeadDemandStatus = LeadDemandStatus.OPEN


class LeadDemandPatchRequest(BaseModel):
    lead_name: str | None = None
    phone: str | None = None
    purpose: LeadPurpose | None = None
    property_type: str | None = None
    city: str | None = None
    neighborhoods: list[str] | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    bedrooms: int | None = Field(default=None, ge=0)
    parking_spaces: int | None = Field(default=None, ge=0)
    min_area: int | None = Field(default=None, ge=0)
    notes: str | None = None
    status: LeadDemandStatus | None = None


class LeadDemandResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    lead_name: str
    phone: str
    purpose: str | None
    property_type: str | None
    city: str | None
    neighborhoods: list[str]
    price_min: Decimal | None
    price_max: Decimal | None
    bedrooms: int | None
    parking_spaces: int | None
    min_area: int | None
    notes: str | None
    status: str
    crm_contact_id: str | None
    crm_deal_id: str | None

    @classmethod
    def from_domain(cls, demand: LeadDemand) -> "LeadDemandResponse":
        return cls(
            id=demand.id,
            tenant_id=demand.tenant_id,
            lead_name=demand.lead_name,
            phone=demand.phone,
            purpose=demand.purpose.value if demand.purpose else None,
            property_type=demand.property_type,
            city=demand.city,
            neighborhoods=demand.neighborhoods,
            price_min=demand.price_min,
            price_max=demand.price_max,
            bedrooms=demand.bedrooms,
            parking_spaces=demand.parking_spaces,
            min_area=demand.min_area,
            notes=demand.notes,
            status=demand.status.value,
            crm_contact_id=demand.crm_contact_id,
            crm_deal_id=demand.crm_deal_id,
        )


@router.post("/demands", response_model=LeadDemandResponse, status_code=status.HTTP_201_CREATED)
def create_demand(
    payload: LeadDemandRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> LeadDemandResponse:
    demand = LeadDemand(
        tenant_id=principal.tenant_id,
        responsible_user_id=principal.user_id,
        **payload.model_dump(),
    )
    saved = SqlAlchemyLeadDemandRepository(session).create(principal.tenant_id, demand)
    return LeadDemandResponse.from_domain(saved)


@router.get("/demands", response_model=list[LeadDemandResponse])
def list_demands(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[LeadDemandResponse]:
    demands = SqlAlchemyLeadDemandRepository(session).list(
        principal.tenant_id, limit=limit, offset=offset
    )
    return [LeadDemandResponse.from_domain(demand) for demand in demands]


@router.get("/demands/{demand_id}", response_model=LeadDemandResponse)
def get_demand(
    demand_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> LeadDemandResponse:
    demand = SqlAlchemyLeadDemandRepository(session).get_by_id(principal.tenant_id, demand_id)
    if demand is None:
        raise NotFoundError("Lead demand not found")
    return LeadDemandResponse.from_domain(demand)


@router.patch("/demands/{demand_id}", response_model=LeadDemandResponse)
def patch_demand(
    demand_id: UUID,
    payload: LeadDemandPatchRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> LeadDemandResponse:
    repo = SqlAlchemyLeadDemandRepository(session)
    demand = repo.get_by_id(principal.tenant_id, demand_id)
    if demand is None:
        raise NotFoundError("Lead demand not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(demand, field, value)
    return LeadDemandResponse.from_domain(repo.update(principal.tenant_id, demand))
