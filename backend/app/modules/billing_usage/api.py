from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    require_roles,
)
from app.modules.billing_usage.adapters.models import (
    AiAttendanceSessionModel,
    AsaasPackOrderModel,
    AsaasSubscriptionModel,
    CommercialPackModel,
    CommercialPlanModel,
    CommercialUsageEventModel,
    CreditLedgerModel,
    UsageRecordModel,
)
from app.modules.billing_usage.asaas import (
    OPEN_SUBSCRIPTION_STATUSES,
    AsaasBillingService,
    AsaasCustomerInput,
    AsaasSubscriptionInput,
    asaas_client_from_settings,
    verify_asaas_webhook_token,
)
from app.modules.billing_usage.commercial import (
    COMMERCIAL_RESOURCES,
    RESOURCE_LABELS,
    CommercialEntitlementService,
    effective_price_cents,
    pack_offers,
)
from app.modules.billing_usage.service import (
    CHAT_RATES_USD_PER_MILLION,
    CREDIT_VALUE_USD,
    DEFAULT_MARKUP_MULTIPLIER,
    IMAGE_TOKEN_RATES_USD_PER_MILLION,
    PRICING_CATALOG_VERSION,
    CreditLedgerService,
)
from app.modules.tenants.adapters.models import TenantModel
from app.modules.users.adapters.models import UserModel
from app.modules.users.domain.entities import UserRole

router = APIRouter(prefix="/usage", tags=["usage"])
billing_router = APIRouter(prefix="/billing", tags=["billing"])
BILLING_TIMEZONE = ZoneInfo("America/Sao_Paulo")
asaas_webhook_router = APIRouter(prefix="/webhooks/asaas", tags=["asaas"])


class UsageSummaryItem(BaseModel):
    type: str
    module: str
    quantity: int
    estimated_cost: Decimal


class CreditAccountResponse(BaseModel):
    tenant_id: UUID
    balance_credits: int
    reserved_credits: int
    available_credits: int
    enforcement_mode: str
    unlimited_messages: bool
    credit_value_usd: Decimal = CREDIT_VALUE_USD
    markup_multiplier: Decimal = DEFAULT_MARKUP_MULTIPLIER


class CreditLedgerItem(BaseModel):
    id: UUID
    delta_credits: int
    balance_after: int
    kind: str
    resource: str | None
    model: str | None
    provider_cost_usd: Decimal
    retail_cost_usd: Decimal
    description: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, model: CreditLedgerModel) -> "CreditLedgerItem":
        return cls.model_validate(model, from_attributes=True)


class PricingCatalogResponse(BaseModel):
    version: str
    credit_value_usd: Decimal
    markup_multiplier: Decimal
    chat_usd_per_million: dict[str, list[Decimal]]
    images_usd_per_million_tokens: dict[str, list[Decimal]]


class CommercialPlanResponse(BaseModel):
    code: str
    name: str
    version: int
    monthly_price_cents: int
    currency: str
    ai_attendances: int
    property_searches: int
    image_optimizations: int
    max_users: int
    is_public: bool


class CommercialPackResponse(BaseModel):
    code: str
    name: str
    resource: str
    units: int
    price_cents: int | None
    currency: str
    active: bool


class CommercialResourceUsageResponse(BaseModel):
    resource: str
    label: str
    granted: int
    consumed: int
    reserved: int
    available: int
    measured: int
    overage: int


class CommercialUsageEventResponse(BaseModel):
    id: UUID
    resource: str
    units: int
    within_allowance: bool
    created_at: datetime


class CommercialUsageResponse(BaseModel):
    plan: CommercialPlanResponse
    status: str
    enforcement_mode: str
    cycle_started_at: datetime
    cycle_ends_at: datetime
    active_ai_attendances: int
    resources: list[CommercialResourceUsageResponse]
    recent_events: list[CommercialUsageEventResponse]


class CommercialCatalogResponse(BaseModel):
    plans: list[CommercialPlanResponse]
    packs: list[CommercialPackResponse]


class AsaasWebhookResponse(BaseModel):
    received: bool = True
    duplicate: bool = False
    outcome: str


@router.get("/summary", response_model=list[UsageSummaryItem])
def usage_summary(
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[UsageSummaryItem]:
    statement = select(
        UsageRecordModel.type,
        UsageRecordModel.module,
        func.sum(UsageRecordModel.quantity).label("quantity"),
        func.sum(UsageRecordModel.estimated_cost).label("estimated_cost"),
    ).where(UsageRecordModel.tenant_id == principal.tenant_id)
    if start:
        statement = statement.where(
            UsageRecordModel.created_at >= datetime.combine(start, time.min)
        )
    if end:
        statement = statement.where(UsageRecordModel.created_at <= datetime.combine(end, time.max))
    rows = session.execute(
        statement.group_by(UsageRecordModel.type, UsageRecordModel.module).order_by(
            UsageRecordModel.module, UsageRecordModel.type
        )
    ).all()
    return [
        UsageSummaryItem(
            type=row.type,
            module=row.module,
            quantity=int(row.quantity or 0),
            estimated_cost=row.estimated_cost or Decimal("0"),
        )
        for row in rows
    ]


@router.get("/credits", response_model=CreditAccountResponse)
def credit_account(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> CreditAccountResponse:
    account = CreditLedgerService(session).account(principal.tenant_id)
    session.commit()
    return CreditAccountResponse(
        tenant_id=account.tenant_id,
        balance_credits=account.balance_credits,
        reserved_credits=account.reserved_credits,
        available_credits=account.balance_credits - account.reserved_credits,
        enforcement_mode=account.enforcement_mode,
        unlimited_messages=account.unlimited_messages,
    )


@router.get("/commercial", response_model=CommercialUsageResponse)
def commercial_usage(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> CommercialUsageResponse:
    service = CommercialEntitlementService(session)
    subscription = service.subscription(principal.tenant_id)
    session.commit()
    plan = session.get(CommercialPlanModel, subscription.plan_id)
    if plan is None:
        raise RuntimeError("Commercial plan not found")
    summaries = service.resource_summary(principal.tenant_id)
    now = datetime.now(UTC)
    active_attendances = int(
        session.scalar(
            select(func.count()).where(
                AiAttendanceSessionModel.tenant_id == principal.tenant_id,
                AiAttendanceSessionModel.status == "active",
                AiAttendanceSessionModel.expires_at > now,
            )
        )
        or 0
    )
    events = session.scalars(
        select(CommercialUsageEventModel)
        .where(CommercialUsageEventModel.tenant_id == principal.tenant_id)
        .order_by(
            CommercialUsageEventModel.created_at.desc(),
            CommercialUsageEventModel.id.desc(),
        )
        .limit(25)
    ).all()
    return CommercialUsageResponse(
        plan=CommercialPlanResponse.model_validate(plan, from_attributes=True),
        status=subscription.status,
        enforcement_mode=subscription.enforcement_mode,
        cycle_started_at=subscription.cycle_started_at,
        cycle_ends_at=subscription.cycle_ends_at,
        active_ai_attendances=active_attendances,
        resources=[
            CommercialResourceUsageResponse(
                resource=resource,
                label=RESOURCE_LABELS[resource],
                **summaries[resource],
            )
            for resource in COMMERCIAL_RESOURCES
        ],
        recent_events=[
            CommercialUsageEventResponse.model_validate(item, from_attributes=True)
            for item in events
        ],
    )


@router.get("/commercial/catalog", response_model=CommercialCatalogResponse)
def commercial_catalog(
    _: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> CommercialCatalogResponse:
    plans = session.scalars(
        select(CommercialPlanModel)
        .where(
            CommercialPlanModel.is_current.is_(True),
            CommercialPlanModel.is_public.is_(True),
        )
        .order_by(CommercialPlanModel.monthly_price_cents, CommercialPlanModel.name)
    ).all()
    packs = session.scalars(
        select(CommercialPackModel).order_by(
            CommercialPackModel.resource, CommercialPackModel.units
        )
    ).all()
    return CommercialCatalogResponse(
        plans=[CommercialPlanResponse.model_validate(item, from_attributes=True) for item in plans],
        packs=[CommercialPackResponse.model_validate(item, from_attributes=True) for item in packs],
    )


@router.get("/credits/ledger", response_model=list[CreditLedgerItem])
def credit_ledger(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[CreditLedgerItem]:
    items = session.scalars(
        select(CreditLedgerModel)
        .where(CreditLedgerModel.tenant_id == principal.tenant_id)
        .order_by(CreditLedgerModel.created_at.desc(), CreditLedgerModel.id.desc())
        .limit(limit)
    ).all()
    return [CreditLedgerItem.from_model(item) for item in items]


@router.get("/pricing", response_model=PricingCatalogResponse)
def pricing_catalog(
    _: CurrentPrincipal = Depends(get_current_principal),
) -> PricingCatalogResponse:
    return PricingCatalogResponse(
        version=PRICING_CATALOG_VERSION,
        credit_value_usd=CREDIT_VALUE_USD,
        markup_multiplier=DEFAULT_MARKUP_MULTIPLIER,
        chat_usd_per_million={
            model: list(rates) for model, rates in CHAT_RATES_USD_PER_MILLION.items()
        },
        images_usd_per_million_tokens={
            model: list(rates) for model, rates in IMAGE_TOKEN_RATES_USD_PER_MILLION.items()
        },
    )


@asaas_webhook_router.post("", response_model=AsaasWebhookResponse)
def receive_asaas_webhook(
    payload: dict[str, Any],
    asaas_access_token: Annotated[str | None, Header(alias="asaas-access-token")] = None,
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> AsaasWebhookResponse:
    verify_asaas_webhook_token(container.settings, asaas_access_token)
    service = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    )
    result = service.process_webhook(payload)
    return AsaasWebhookResponse(duplicate=result.duplicate, outcome=result.outcome)


class BillingPlan(BaseModel):
    code: str
    name: str
    # What this tenant pays (the beta price when on beta pricing) and the regular price.
    monthly_price_cents: int
    list_price_cents: int
    ai_attendances: int
    property_searches: int
    image_optimizations: int
    max_users: int


class BillingSubscription(BaseModel):
    id: UUID
    plan_code: str
    plan_name: str
    billing_type: str
    status: str
    value_cents: int
    next_due_date: date
    invoice_url: str | None


class BillingContact(BaseModel):
    name: str
    email: str | None
    cpf_cnpj: str | None


class PackOffer(BaseModel):
    resource: str
    units: int
    price_cents: int


class PackOrder(BaseModel):
    id: UUID
    resource: str
    units: int
    value_cents: int
    status: str
    invoice_url: str | None
    created_at: datetime


class BillingOverview(BaseModel):
    status: str
    beta_pricing: bool
    plan: BillingPlan
    trial_ends_at: datetime | None
    cycle_ends_at: datetime
    payments_enabled: bool
    plans: list[BillingPlan]
    subscription: BillingSubscription | None
    contact: BillingContact
    packs: list[PackOffer]
    pack_orders: list[PackOrder]


class SelfServiceCustomer(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    cpf_cnpj: str = Field(min_length=11, max_length=18)
    mobile_phone: str | None = Field(default=None, max_length=24)

    @field_validator("cpf_cnpj")
    @classmethod
    def normalize_cpf_cnpj(cls, value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) not in {11, 14}:
            raise ValueError("Informe um CPF ou CNPJ válido")
        return digits


class SelfServiceSubscriptionRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=80)
    billing_type: str = Field(pattern="^(PIX|CREDIT_CARD)$")
    idempotency_key: str = Field(min_length=8, max_length=200)
    customer: SelfServiceCustomer


def _billing_plan(plan: CommercialPlanModel, *, beta: bool) -> BillingPlan:
    return BillingPlan(
        code=plan.code,
        name=plan.name,
        monthly_price_cents=effective_price_cents(plan, beta=beta),
        list_price_cents=plan.monthly_price_cents,
        ai_attendances=plan.ai_attendances,
        property_searches=plan.property_searches,
        image_optimizations=plan.image_optimizations,
        max_users=plan.max_users,
    )


def _pack_order(order: AsaasPackOrderModel) -> PackOrder:
    return PackOrder.model_validate(order, from_attributes=True)


def _billing_overview(session: Session, tenant_id: UUID, container: Container) -> BillingOverview:
    commercial = CommercialEntitlementService(session).subscription(tenant_id)
    session.commit()
    current_plan = session.get(CommercialPlanModel, commercial.plan_id)
    if current_plan is None:
        raise RuntimeError("Commercial plan not found")
    plans = session.scalars(
        select(CommercialPlanModel)
        .where(
            CommercialPlanModel.is_current.is_(True),
            CommercialPlanModel.is_public.is_(True),
            CommercialPlanModel.monthly_price_cents > 0,
        )
        .order_by(CommercialPlanModel.monthly_price_cents)
    ).all()
    beta = commercial.beta_pricing
    subscribed = commercial.status in {"active", "past_due"} and current_plan.is_public
    orders = session.scalars(
        select(AsaasPackOrderModel)
        .where(
            AsaasPackOrderModel.tenant_id == tenant_id,
            AsaasPackOrderModel.status.in_(("pending_payment", "paid")),
        )
        .order_by(AsaasPackOrderModel.created_at.desc())
        .limit(5)
    ).all()
    latest = session.execute(
        select(AsaasSubscriptionModel, CommercialPlanModel)
        .join(CommercialPlanModel, CommercialPlanModel.id == AsaasSubscriptionModel.plan_id)
        .where(
            AsaasSubscriptionModel.tenant_id == tenant_id,
            AsaasSubscriptionModel.status.in_(OPEN_SUBSCRIPTION_STATUSES),
        )
        .order_by(AsaasSubscriptionModel.created_at.desc())
        .limit(1)
    ).first()
    tenant = session.get(TenantModel, tenant_id)
    settings = tenant.settings if tenant is not None and isinstance(tenant.settings, dict) else {}
    profile = settings.get("profile") if isinstance(settings.get("profile"), dict) else {}
    admin_email = session.scalar(
        select(UserModel.email)
        .where(UserModel.tenant_id == tenant_id, UserModel.is_master.is_(True))
        .limit(1)
    )
    return BillingOverview(
        status=commercial.status,
        beta_pricing=beta,
        plan=_billing_plan(current_plan, beta=beta),
        trial_ends_at=commercial.trial_ends_at,
        cycle_ends_at=commercial.cycle_ends_at,
        payments_enabled=container.settings.asaas_api_key is not None,
        plans=[_billing_plan(plan, beta=beta) for plan in plans],
        packs=[PackOffer(**offer) for offer in pack_offers(current_plan)] if subscribed else [],
        pack_orders=[_pack_order(order) for order in orders],
        subscription=(
            BillingSubscription(
                id=latest[0].id,
                plan_code=latest[1].code,
                plan_name=latest[1].name,
                billing_type=latest[0].billing_type,
                status=latest[0].status,
                value_cents=latest[0].value_cents,
                next_due_date=latest[0].next_due_date,
                invoice_url=latest[0].invoice_url,
            )
            if latest
            else None
        ),
        contact=BillingContact(
            name=profile.get("legal_name")
            or profile.get("display_name")
            or (tenant.name if tenant else ""),
            email=admin_email,
            cpf_cnpj=profile.get("document_number"),
        ),
    )


@billing_router.get("", response_model=BillingOverview)
def billing_overview(
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> BillingOverview:
    return _billing_overview(session, principal.tenant_id, container)


class PixCharge(BaseModel):
    payment_id: str
    value_cents: int
    due_date: date | None
    payload: str
    encoded_image: str
    expiration_date: datetime | None


@billing_router.get("/pix", response_model=PixCharge)
def billing_pix(
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> PixCharge:
    """PIX QR code for the open charge, so the agency pays without leaving the app."""

    charge = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    ).pix_for_open_charge(principal.tenant_id)
    return PixCharge(
        payment_id=charge["payment_id"],
        value_cents=round(Decimal(str(charge["value"] or 0)) * 100),
        due_date=charge["due_date"],
        payload=charge["payload"],
        encoded_image=charge["encoded_image"],
        expiration_date=charge["expiration_date"],
    )


class PackOrderRequest(BaseModel):
    resource: str = Field(pattern="^(ai_attendance|property_search_standard|image_optimization)$")
    idempotency_key: str = Field(min_length=8, max_length=200)


@billing_router.post("/packs", response_model=PackOrder, status_code=201)
def buy_pack(
    payload: PackOrderRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN, UserRole.GESTOR)),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> PackOrder:
    """One-off charge for extra allowance; it is credited when the payment arrives."""

    order = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    ).create_pack_order(
        principal.tenant_id, resource=payload.resource, idempotency_key=payload.idempotency_key
    )
    return _pack_order(order)


@billing_router.get("/packs/{order_id}/pix", response_model=PixCharge)
def pack_pix(
    order_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> PixCharge:
    charge = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    ).pix_for_pack_order(principal.tenant_id, order_id)
    return PixCharge(
        payment_id=charge["payment_id"],
        value_cents=round(Decimal(str(charge["value"] or 0)) * 100),
        due_date=charge["due_date"],
        payload=charge["payload"],
        encoded_image=charge["encoded_image"],
        expiration_date=charge["expiration_date"],
    )


@billing_router.post("/subscription", response_model=BillingOverview, status_code=201)
def subscribe(
    payload: SelfServiceSubscriptionRequest,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN)),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> BillingOverview:
    """The agency subscribes itself; the plan is activated by the payment webhook."""

    service = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    )
    service.create_subscription(
        principal.tenant_id,
        AsaasSubscriptionInput(
            plan_code=payload.plan_code,
            billing_type=payload.billing_type,
            next_due_date=datetime.now(BILLING_TIMEZONE).date(),
            enforcement_mode="enforce",
            idempotency_key=payload.idempotency_key,
            customer=AsaasCustomerInput(
                name=payload.customer.name,
                email=str(payload.customer.email),
                cpf_cnpj=payload.customer.cpf_cnpj,
                mobile_phone=payload.customer.mobile_phone,
                # Self-service customers get the monthly charge e-mails from Asaas.
                notification_disabled=False,
            ),
        ),
    )
    return _billing_overview(session, principal.tenant_id, container)
