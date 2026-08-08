from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.contacts.phone import normalize_contact_phone
from app.modules.contacts.service import ContactUpsertService
from app.modules.conversations.adapters.models import ConversationModel
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.domain.entities import LeadDemand, LeadDemandStatus, LeadPurpose
from app.shared.errors.exceptions import ConflictError, NotFoundError

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
    conversation_id: UUID | None = None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return normalize_contact_phone(value)


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
    conversation_id: UUID | None = None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        return normalize_contact_phone(value) if value is not None else None


class LeadDemandResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    contact_id: UUID | None
    conversation_id: UUID | None
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
            contact_id=demand.contact_id,
            conversation_id=demand.conversation_id,
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
    values = payload.model_dump()
    conversation = _validated_conversation(
        session, principal.tenant_id, values.get("conversation_id"), values["phone"]
    )
    if conversation is not None:
        values["phone"] = conversation.phone
    repo = SqlAlchemyLeadDemandRepository(session)
    repo.lock_phone(principal.tenant_id, values["phone"])
    contact = ContactUpsertService(session).upsert(
        principal.tenant_id,
        phone=values["phone"],
        name=values["lead_name"],
        interest=values.get("notes"),
        source="manual",
    )
    values["phone"] = contact.phone
    if repo.get_open_by_phone(principal.tenant_id, contact.phone) is not None:
        raise ConflictError("Já existe uma demanda aberta para este contato")
    demand = LeadDemand(
        tenant_id=principal.tenant_id,
        responsible_user_id=principal.user_id,
        contact_id=contact.id,
        **values,
    )
    saved = repo.create(principal.tenant_id, demand)
    return LeadDemandResponse.from_domain(saved)


@router.get("/demands", response_model=list[LeadDemandResponse])
def list_demands(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    contact_id: UUID | None = None,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[LeadDemandResponse]:
    demands = SqlAlchemyLeadDemandRepository(session).list(
        principal.tenant_id,
        limit=limit,
        offset=offset,
        contact_id=contact_id,
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
        if field == "phone" and value is not None:
            value = normalize_contact_phone(value)
        setattr(demand, field, value)
    conversation = _validated_conversation(
        session, principal.tenant_id, demand.conversation_id, demand.phone
    )
    if conversation is not None:
        demand.phone = conversation.phone
    elif "phone" in payload.model_fields_set:
        demand.conversation_id = None
    repo.lock_phone(principal.tenant_id, demand.phone)
    duplicate = repo.get_open_by_phone(principal.tenant_id, demand.phone)
    if duplicate is not None and duplicate.id != demand.id:
        raise ConflictError("Já existe uma demanda aberta para este contato")
    contact = ContactUpsertService(session).upsert(
        principal.tenant_id,
        phone=demand.phone,
        name=demand.lead_name,
        interest=demand.notes,
        source="manual",
    )
    demand.phone = contact.phone
    demand.contact_id = contact.id
    return LeadDemandResponse.from_domain(repo.update(principal.tenant_id, demand))


def _validated_conversation(
    session: Session,
    tenant_id: UUID,
    conversation_id: UUID | None,
    phone: str,
) -> ConversationModel | None:
    if conversation_id is None:
        return None
    conversation = session.scalar(
        select(ConversationModel).where(
            ConversationModel.tenant_id == tenant_id,
            ConversationModel.id == conversation_id,
        )
    )
    if conversation is None:
        raise NotFoundError("Conversation not found")
    if normalize_contact_phone(phone) != conversation.phone:
        raise ConflictError("A conversa não pertence à identidade informada")
    return conversation
