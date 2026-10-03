"""ImmobIA network: agencies share listings with each other and agree on partnerships.

Owner data and the exact address never leave the owning agency. Contacts are only
revealed to both sides after the owner accepts a partnership request.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    require_roles,
)
from app.modules.billing_usage.adapters.models import CommercialPlanModel
from app.modules.billing_usage.commercial import CommercialEntitlementService
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.network.models import NetworkMembershipModel, PartnershipRequestModel
from app.modules.properties.adapters.models import PropertyImageModel, PropertyModel
from app.modules.properties.adapters.repositories import _to_domain
from app.modules.properties.api import serve_property_image
from app.modules.properties.application.matching import (
    calculate_property_match,
    meets_required_constraints,
    property_offer_price,
)
from app.modules.tenants.adapters.models import TenantModel
from app.modules.users.domain.entities import UserRole
from app.shared.errors.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PaymentRequiredError,
)

router = APIRouter(prefix="/network", tags=["network"])

TERMS_VERSION = "2026-10-02"
TERMS_TEXT = (
    "Ao participar da Rede ImmobIA, a imobiliária declara que tem autorização dos "
    "proprietários para divulgar os imóveis que compartilhar e que manterá esses dados "
    "atualizados. Imóveis de parceiros só podem ser apresentados a clientes depois que a "
    "parceria for aceita pela imobiliária responsável. A divisão de comissão informada vale "
    "para os pedidos feitos enquanto ela estiver em vigor, e o acerto é feito diretamente "
    "entre as imobiliárias, sem intermediação financeira do ImmobIA. Os contatos recebidos "
    "por meio da rede só podem ser usados para a negociação do imóvel e não podem ser "
    "repassados a terceiros. O ImmobIA não exibe dados do proprietário nem o endereço exato, "
    "mas cada imobiliária é responsável pelo que escreve no título e na descrição."
)
MAX_RESULTS = 50
MAX_IMAGES = 12


class NetworkRequiresPaidPlan(PaymentRequiredError):
    code = "network_requires_paid_plan"


class NetworkContact(BaseModel):
    agency_name: str
    name: str
    phone: str
    email: str


class NetworkSettingsResponse(BaseModel):
    eligible: bool
    terms_version: str
    terms_text: str
    member: bool
    terms_accepted_at: datetime | None = None
    partner_commission_percent: int | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    shared_properties: int = 0
    pending_received: int = 0


class NetworkSettingsRequest(BaseModel):
    accept_terms: Literal[True]
    partner_commission_percent: int = Field(ge=1, le=99)
    contact_name: str = Field(min_length=2, max_length=160)
    contact_phone: str = Field(min_length=8, max_length=30)
    contact_email: EmailStr


class ShareRequest(BaseModel):
    shared: bool


class ShareResponse(BaseModel):
    property_id: UUID
    network_shared: bool


class NetworkPartnershipRef(BaseModel):
    id: UUID
    status: str


class NetworkListing(BaseModel):
    id: UUID
    title: str
    description: str | None
    purpose: str | None
    property_type: str | None
    city: str
    neighborhood: str | None
    price: Decimal | None
    sale_price: Decimal | None
    rent_price: Decimal | None
    bedrooms: int | None
    suites: int | None
    bathrooms: int | None
    parking_spaces: int | None
    area: int | None
    image_ids: list[UUID]
    agency_name: str
    partner_commission_percent: int
    fit_score: int
    matched: list[str]
    tradeoffs: list[str]
    partnership: NetworkPartnershipRef | None


class PartnershipCreateRequest(BaseModel):
    property_id: UUID
    demand_id: UUID | None = None
    message: str | None = Field(default=None, max_length=1000)


class PartnershipResponse(BaseModel):
    id: UUID
    direction: Literal["sent", "received"]
    status: str
    property_id: UUID
    property_title: str
    partner_commission_percent: int
    message: str | None
    counterpart_agency: str
    # Only after the owner accepts.
    counterpart_contact: NetworkContact | None
    created_at: datetime
    decided_at: datetime | None


class PartnershipListResponse(BaseModel):
    received: list[PartnershipResponse]
    sent: list[PartnershipResponse]


def has_paid_plan(session: Session, tenant_id: UUID) -> bool:
    subscription = CommercialEntitlementService(session).subscription(tenant_id)
    plan = session.get(CommercialPlanModel, subscription.plan_id)
    return (
        plan is not None
        and plan.monthly_price_cents > 0
        and subscription.status in {"active", "past_due"}
    )


def _require_paid_plan(session: Session, tenant_id: UUID) -> None:
    if not has_paid_plan(session, tenant_id):
        raise NetworkRequiresPaidPlan("A Rede ImmobIA está disponível nos planos pagos.")


def _membership(session: Session, tenant_id: UUID) -> NetworkMembershipModel | None:
    return session.get(NetworkMembershipModel, tenant_id)


def _require_membership(session: Session, tenant_id: UUID) -> NetworkMembershipModel:
    membership = _membership(session, tenant_id)
    if membership is None:
        raise ConflictError("Aceite o termo da Rede ImmobIA em Configurações antes de continuar.")
    return membership


def _agency_name(tenant: TenantModel | None) -> str:
    if tenant is None:
        return "Imobiliária"
    profile = tenant.settings.get("profile") if isinstance(tenant.settings, dict) else None
    if isinstance(profile, dict) and profile.get("display_name"):
        return str(profile["display_name"])
    return tenant.name


def _visible_shared_property(session: Session, property_id: UUID) -> PropertyModel:
    """A listing other members may see: shared, active, owned by a paying active member."""

    model = session.get(PropertyModel, property_id)
    if (
        model is None
        or not model.network_shared
        or model.status != "active"
        or _membership(session, model.tenant_id) is None
    ):
        raise NotFoundError("Imóvel não encontrado na Rede ImmobIA")
    owner = session.get(TenantModel, model.tenant_id)
    if owner is None or owner.status != "active" or not has_paid_plan(session, model.tenant_id):
        raise NotFoundError("Imóvel não encontrado na Rede ImmobIA")
    return model


@router.get("/settings", response_model=NetworkSettingsResponse)
def network_settings(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> NetworkSettingsResponse:
    eligible = has_paid_plan(session, principal.tenant_id)
    session.commit()
    membership = _membership(session, principal.tenant_id)
    shared = session.scalars(
        select(PropertyModel.id).where(
            PropertyModel.tenant_id == principal.tenant_id, PropertyModel.network_shared
        )
    ).all()
    pending = session.scalars(
        select(PartnershipRequestModel.id).where(
            PartnershipRequestModel.owner_tenant_id == principal.tenant_id,
            PartnershipRequestModel.status == "pending",
        )
    ).all()
    return NetworkSettingsResponse(
        eligible=eligible,
        terms_version=TERMS_VERSION,
        terms_text=TERMS_TEXT,
        member=membership is not None,
        terms_accepted_at=membership.accepted_at if membership else None,
        partner_commission_percent=membership.partner_commission_percent if membership else None,
        contact_name=membership.contact_name if membership else None,
        contact_phone=membership.contact_phone if membership else None,
        contact_email=membership.contact_email if membership else None,
        shared_properties=len(shared),
        pending_received=len(pending),
    )


@router.put("/settings", response_model=NetworkSettingsResponse)
def update_network_settings(
    payload: NetworkSettingsRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    session: Session = Depends(get_db_session),
) -> NetworkSettingsResponse:
    _require_paid_plan(session, principal.tenant_id)
    membership = _membership(session, principal.tenant_id)
    now = datetime.now(UTC)
    if membership is None:
        membership = NetworkMembershipModel(tenant_id=principal.tenant_id)
        session.add(membership)
    if membership.terms_version != TERMS_VERSION or membership.accepted_at is None:
        membership.accepted_at = now
        membership.accepted_by_user_id = principal.user_id
    membership.terms_version = TERMS_VERSION
    membership.partner_commission_percent = payload.partner_commission_percent
    membership.contact_name = payload.contact_name.strip()
    membership.contact_phone = payload.contact_phone.strip()
    membership.contact_email = str(payload.contact_email)
    session.commit()
    return network_settings(principal, session)


@router.put("/properties/{property_id}/share", response_model=ShareResponse)
def share_property(
    property_id: UUID,
    payload: ShareRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN, UserRole.GESTOR)),
    session: Session = Depends(get_db_session),
) -> ShareResponse:
    model = session.scalar(
        select(PropertyModel)
        .where(PropertyModel.tenant_id == principal.tenant_id, PropertyModel.id == property_id)
        .with_for_update()
    )
    if model is None:
        raise NotFoundError("Imóvel não encontrado")
    if payload.shared:
        _require_paid_plan(session, principal.tenant_id)
        _require_membership(session, principal.tenant_id)
        if model.source != "manual":
            raise ConflictError("Só imóveis da própria carteira podem ser compartilhados")
        if model.status != "active":
            raise ConflictError("Ative o imóvel antes de compartilhar")
        if model.price is None and model.sale_price is None and model.rent_price is None:
            raise ConflictError("Informe o preço antes de compartilhar")
        has_image = session.scalar(
            select(PropertyImageModel.id)
            .where(
                PropertyImageModel.tenant_id == principal.tenant_id,
                PropertyImageModel.property_id == property_id,
                PropertyImageModel.status != "failed",
            )
            .limit(1)
        )
        if has_image is None:
            raise ConflictError("Adicione ao menos uma foto antes de compartilhar")
        if not model.network_shared:
            model.network_shared_at = datetime.now(UTC)
        model.network_shared = True
    else:
        model.network_shared = False
        model.network_shared_at = None
    session.commit()
    return ShareResponse(property_id=model.id, network_shared=model.network_shared)


@router.get("/search", response_model=list[NetworkListing])
def search_network(
    demand_id: Annotated[UUID, Query()],
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[NetworkListing]:
    """Shared listings of other agencies that fit the demand, ranked like the Buscador."""

    _require_paid_plan(session, principal.tenant_id)
    demand = SqlAlchemyLeadDemandRepository(session).get_by_id(principal.tenant_id, demand_id)
    if demand is None:
        raise NotFoundError("Lead demand not found")
    rows = session.execute(
        select(PropertyModel, TenantModel, NetworkMembershipModel)
        .join(TenantModel, TenantModel.id == PropertyModel.tenant_id)
        .join(NetworkMembershipModel, NetworkMembershipModel.tenant_id == PropertyModel.tenant_id)
        .where(
            PropertyModel.network_shared,
            PropertyModel.status == "active",
            PropertyModel.tenant_id != principal.tenant_id,
            TenantModel.status == "active",
        )
    ).all()
    paying: dict[UUID, bool] = {}
    ranked = []
    for model, tenant, membership in rows:
        if tenant.id not in paying:
            paying[tenant.id] = has_paid_plan(session, tenant.id)
        if not paying[tenant.id]:
            continue
        property_ = _to_domain(model)
        if not meets_required_constraints(property_, demand):
            continue
        ranked.append((calculate_property_match(property_, demand), model, tenant, membership))
    ranked.sort(key=lambda item: (item[0].score, item[1].updated_at), reverse=True)
    ranked = ranked[:MAX_RESULTS]
    property_ids = [item[1].id for item in ranked]
    images: dict[UUID, list[UUID]] = {}
    if property_ids:
        for image in session.scalars(
            select(PropertyImageModel)
            .where(
                PropertyImageModel.property_id.in_(property_ids),
                PropertyImageModel.status != "failed",
            )
            .order_by(PropertyImageModel.is_primary.desc(), PropertyImageModel.sort_order)
        ):
            images.setdefault(image.property_id, []).append(image.id)
    partnerships = {
        request.property_id: request
        for request in session.scalars(
            select(PartnershipRequestModel).where(
                PartnershipRequestModel.requester_tenant_id == principal.tenant_id,
                PartnershipRequestModel.property_id.in_(property_ids or [uuid4()]),
                PartnershipRequestModel.status.in_(("pending", "accepted")),
            )
        )
    }
    purpose = demand.purpose.value if demand.purpose else None
    session.commit()
    return [
        NetworkListing(
            id=model.id,
            title=model.title,
            description=model.description,
            purpose=model.purpose,
            property_type=model.property_type,
            city=model.city,
            neighborhood=model.neighborhood,
            price=property_offer_price(match.property, purpose),
            sale_price=model.sale_price,
            rent_price=model.rent_price,
            bedrooms=model.bedrooms,
            suites=model.suites,
            bathrooms=model.bathrooms,
            parking_spaces=model.parking_spaces,
            area=model.area,
            image_ids=images.get(model.id, [])[:MAX_IMAGES],
            agency_name=_agency_name(tenant),
            partner_commission_percent=membership.partner_commission_percent,
            fit_score=match.score,
            matched=match.matched,
            tradeoffs=match.tradeoffs,
            partnership=(
                NetworkPartnershipRef(
                    id=partnerships[model.id].id, status=partnerships[model.id].status
                )
                if model.id in partnerships
                else None
            ),
        )
        for match, model, tenant, membership in ranked
    ]


@router.get("/properties/{property_id}/images/{image_id}/content")
def network_property_image(
    property_id: UUID,
    image_id: UUID,
    variant: Annotated[str, Query(pattern="^(original|display)$")] = "display",
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
):
    """Photos of a shared listing, readable by paying members only while it stays shared."""

    if not has_paid_plan(session, principal.tenant_id):
        session.commit()
        raise NetworkRequiresPaidPlan("A Rede ImmobIA está disponível nos planos pagos.")
    model = _visible_shared_property(session, property_id)
    image = session.scalar(
        select(PropertyImageModel).where(
            PropertyImageModel.tenant_id == model.tenant_id,
            PropertyImageModel.property_id == property_id,
            PropertyImageModel.id == image_id,
        )
    )
    session.commit()
    if image is None:
        raise NotFoundError("Foto não encontrada")
    return serve_property_image(image, model.tenant_id, variant, container)


@router.post("/partnerships", response_model=PartnershipResponse, status_code=201)
def request_partnership(
    payload: PartnershipCreateRequest,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
) -> PartnershipResponse:
    _require_paid_plan(session, principal.tenant_id)
    _require_membership(session, principal.tenant_id)
    model = _visible_shared_property(session, payload.property_id)
    if model.tenant_id == principal.tenant_id:
        raise ConflictError("Este imóvel já é da sua carteira")
    owner_membership = _require_membership(session, model.tenant_id)
    request = PartnershipRequestModel(
        id=uuid4(),
        property_id=model.id,
        owner_tenant_id=model.tenant_id,
        requester_tenant_id=principal.tenant_id,
        requested_by_user_id=principal.user_id,
        demand_id=payload.demand_id,
        message=(payload.message or "").strip() or None,
        status="pending",
        partner_commission_percent=owner_membership.partner_commission_percent,
        property_title=model.title,
    )
    session.add(request)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "Já existe um pedido de parceria em andamento para este imóvel"
        ) from exc
    session.refresh(request)
    return _partnership_response(session, request, principal.tenant_id)


@router.get("/partnerships", response_model=PartnershipListResponse)
def list_partnerships(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PartnershipListResponse:
    requests = session.scalars(
        select(PartnershipRequestModel)
        .where(
            or_(
                PartnershipRequestModel.owner_tenant_id == principal.tenant_id,
                PartnershipRequestModel.requester_tenant_id == principal.tenant_id,
            )
        )
        .order_by(PartnershipRequestModel.created_at.desc())
        .limit(200)
    ).all()
    items = [_partnership_response(session, item, principal.tenant_id) for item in requests]
    return PartnershipListResponse(
        received=[item for item in items if item.direction == "received"],
        sent=[item for item in items if item.direction == "sent"],
    )


@router.post("/partnerships/{request_id}/{action}", response_model=PartnershipResponse)
def decide_partnership(
    request_id: UUID,
    action: Literal["accept", "decline", "cancel"],
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR, UserRole.CORRETOR)
    ),
    session: Session = Depends(get_db_session),
) -> PartnershipResponse:
    request = session.scalar(
        select(PartnershipRequestModel)
        .where(PartnershipRequestModel.id == request_id)
        .with_for_update()
    )
    if request is None or principal.tenant_id not in {
        request.owner_tenant_id,
        request.requester_tenant_id,
    }:
        raise NotFoundError("Pedido de parceria não encontrado")
    if request.status != "pending":
        raise ConflictError("Este pedido já foi respondido")
    if action == "cancel":
        if principal.tenant_id != request.requester_tenant_id:
            raise ForbiddenError("Só quem fez o pedido pode cancelá-lo")
        request.status = "cancelled"
    else:
        if principal.tenant_id != request.owner_tenant_id:
            raise ForbiddenError("Só a imobiliária do imóvel pode responder ao pedido")
        if principal.role not in {UserRole.ADMIN, UserRole.GESTOR}:
            raise ForbiddenError("Somente administradores e gestores respondem a parcerias")
        request.status = "accepted" if action == "accept" else "declined"
    request.decided_by_user_id = principal.user_id
    request.decided_at = datetime.now(UTC)
    session.commit()
    return _partnership_response(session, request, principal.tenant_id)


def _partnership_response(
    session: Session, request: PartnershipRequestModel, viewer_tenant_id: UUID
) -> PartnershipResponse:
    received = request.owner_tenant_id == viewer_tenant_id
    counterpart_id = request.requester_tenant_id if received else request.owner_tenant_id
    counterpart_agency = _agency_name(session.get(TenantModel, counterpart_id))
    contact = None
    if request.status == "accepted":
        membership = _membership(session, counterpart_id)
        if membership is not None:
            contact = NetworkContact(
                agency_name=counterpart_agency,
                name=membership.contact_name,
                phone=membership.contact_phone,
                email=membership.contact_email,
            )
    return PartnershipResponse(
        id=request.id,
        direction="received" if received else "sent",
        status=request.status,
        property_id=request.property_id,
        property_title=request.property_title,
        partner_commission_percent=request.partner_commission_percent,
        message=request.message,
        counterpart_agency=counterpart_agency,
        counterpart_contact=contact,
        created_at=request.created_at,
        decided_at=request.decided_at,
    )
