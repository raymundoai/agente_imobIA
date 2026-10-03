import hmac
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, Header, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.billing_usage.adapters.models import (
    AsaasSubscriptionModel,
    CommercialEntitlementGrantModel,
    CommercialPackModel,
    CommercialPlanModel,
    CreditAccountModel,
    CreditLedgerModel,
    UsageRecordModel,
)
from app.modules.billing_usage.asaas import (
    AsaasBillingService,
    AsaasCustomerInput,
    AsaasSubscriptionInput,
    asaas_client_from_settings,
)
from app.modules.billing_usage.commercial import (
    COMMERCIAL_RESOURCES,
    CommercialEntitlementService,
)
from app.modules.billing_usage.service import CreditLedgerService
from app.modules.contacts.models import ContactModel
from app.modules.conversations.adapters.models import ConversationModel
from app.modules.leads.adapters.models import LeadDemandModel
from app.modules.platform.models import PlatformUserModel
from app.modules.properties.adapters.models import PropertyModel
from app.modules.tenants.adapters.models import TenantModel
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.modules.tenants.api.schemas import CreateTenantRequest
from app.modules.tenants.application.use_cases import CreateTenantUseCase
from app.modules.users.adapters.models import UserModel
from app.shared.errors.exceptions import AuthenticationError, ConfigurationError, NotFoundError
from app.shared.security.rate_limit import client_ip

router = APIRouter(prefix="/platform", tags=["platform"])


class PlatformCredentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class BootstrapRequest(PlatformCredentials):
    name: str = Field(min_length=2, max_length=160)


class PlatformTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 28800


class PlatformDashboardResponse(BaseModel):
    total_clients: int
    active_clients: int
    inactive_clients: int
    total_users: int
    conversations: int
    leads: int
    properties: int
    contacts: int
    ai_calls: int
    estimated_ai_cost: Decimal
    credits_outstanding: int


class PlatformTenantSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    users: int
    conversations: int
    leads: int
    properties: int
    contacts: int
    ai_calls: int
    estimated_ai_cost: Decimal
    credit_balance: int
    credit_reserved: int
    credit_available: int
    credit_enforcement: str
    unlimited_messages: bool
    commercial_plan: str
    commercial_status: str
    commercial_enforcement: str
    commercial_cycle_ends_at: datetime
    commercial_available: dict[str, int]
    integrations: dict[str, str]


class TenantStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|inactive)$")


class CreditGrantRequest(BaseModel):
    credits: int = Field(gt=0, le=1_000_000_000)
    description: str = Field(min_length=3, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=200)


class CreditSettingsRequest(BaseModel):
    enforcement_mode: str = Field(pattern="^(meter_only|enforce)$")
    unlimited_messages: bool = False


class CommercialPlanItem(BaseModel):
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


class CommercialPackItem(BaseModel):
    code: str
    name: str
    resource: str
    units: int
    price_cents: int | None
    currency: str
    active: bool


class CommercialSubscriptionRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=80)
    enforcement_mode: str = Field(pattern="^(meter_only|enforce)$")
    status: str | None = Field(default=None, pattern="^(pilot|active|past_due|cancelled)$")


class CommercialGrantRequest(BaseModel):
    resource: str
    quantity: int = Field(gt=0, le=1_000_000)
    source: str = Field(default="manual", pattern="^(manual|promotion)$")
    idempotency_key: str = Field(min_length=8, max_length=200)
    reference: str | None = Field(default=None, max_length=300)
    expires_at: datetime | None = None


class CommercialPackGrantRequest(BaseModel):
    pack_code: str = Field(min_length=2, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=200)
    expires_at: datetime | None = None


class AsaasCustomerRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    cpf_cnpj: str = Field(min_length=11, max_length=18)
    mobile_phone: str | None = Field(default=None, max_length=24)
    notification_disabled: bool = True

    @field_validator("cpf_cnpj")
    @classmethod
    def normalize_cpf_cnpj(cls, value: str) -> str:
        normalized = "".join(character for character in value if character.isdigit())
        if len(normalized) not in {11, 14}:
            raise ValueError("cpf_cnpj deve conter 11 ou 14 dígitos")
        return normalized


class AsaasSubscriptionRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=80)
    billing_type: str = Field(default="PIX", pattern="^(UNDEFINED|BOLETO|CREDIT_CARD|PIX)$")
    next_due_date: date
    enforcement_mode: str = Field(default="enforce", pattern="^(meter_only|enforce)$")
    idempotency_key: str = Field(min_length=8, max_length=200)
    customer: AsaasCustomerRequest

    @field_validator("next_due_date")
    @classmethod
    def next_due_date_must_not_be_past(cls, value: date) -> date:
        if value < datetime.now(UTC).date():
            raise ValueError("next_due_date não pode estar no passado")
        return value


class AsaasSubscriptionResponse(BaseModel):
    id: UUID
    provider_customer_id: str
    provider_subscription_id: str | None
    provider_payment_id: str | None
    plan_code: str
    billing_type: str
    value_cents: int
    next_due_date: date
    enforcement_mode: str
    status: str
    invoice_url: str | None
    last_error: str | None
    created_at: datetime


class AsaasIntegrationStatusResponse(BaseModel):
    configured: bool
    environment_url: str | None = None
    account_id: str | None = None
    account_name: str | None = None
    webhook_url: str | None = None
    webhook_notification_email: str | None = None
    # Where the webhook must point now; differs from webhook_url after BACKEND_PUBLIC_URL changes.
    expected_webhook_url: str | None = None


class AsaasWebhookProvisionRequest(BaseModel):
    notification_email: EmailStr


class AsaasWebhookProvisionResponse(BaseModel):
    provider_webhook_id: str
    url: str
    enabled: bool


class CommercialGrantResponse(BaseModel):
    id: UUID
    resource: str
    source: str
    quantity: int
    consumed_units: int
    reserved_units: int
    reference: str | None
    expires_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, model: CommercialEntitlementGrantModel) -> "CommercialGrantResponse":
        return cls.model_validate(model, from_attributes=True)


class PlatformCreditTransaction(BaseModel):
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
    def from_model(cls, model: CreditLedgerModel) -> "PlatformCreditTransaction":
        return cls.model_validate(model, from_attributes=True)


@dataclass(frozen=True, slots=True)
class PlatformPrincipal:
    user_id: UUID
    email: str


def _platform_token(container: Container, user: PlatformUserModel) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": "platform_admin",
            "type": "platform_access",
            "iat": now,
            "exp": now + timedelta(hours=8),
        },
        container.settings.jwt_secret.get_secret_value(),
        algorithm=container.settings.jwt_algorithm,
    )


def get_platform_principal(
    authorization: Annotated[str | None, Header()] = None,
    container: Container = Depends(get_container),
) -> PlatformPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Platform authentication required")
    try:
        payload = jwt.decode(
            authorization[7:],
            container.settings.jwt_secret.get_secret_value(),
            algorithms=[container.settings.jwt_algorithm],
        )
        if payload.get("type") != "platform_access" or payload.get("role") != "platform_admin":
            raise AuthenticationError("Invalid platform token")
        return PlatformPrincipal(user_id=UUID(payload["sub"]), email=str(payload["email"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired platform token") from exc


@router.post(
    "/auth/bootstrap",
    response_model=PlatformTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_platform_admin(
    payload: BootstrapRequest,
    bootstrap_token: Annotated[str | None, Header(alias="X-Platform-Bootstrap-Token")] = None,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PlatformTokenResponse:
    configured = container.settings.platform_bootstrap_token
    if configured is None:
        raise ConfigurationError("Platform bootstrap is disabled")
    if bootstrap_token is None or not hmac.compare_digest(
        bootstrap_token, configured.get_secret_value()
    ):
        raise AuthenticationError("Invalid platform bootstrap token")
    if session.scalar(select(func.count()).select_from(PlatformUserModel)):
        raise AuthenticationError("Platform has already been bootstrapped")
    user = PlatformUserModel(
        id=uuid4(),
        name=payload.name.strip(),
        email=payload.email.lower(),
        hashed_password=container.password_hasher.hash(payload.password),
    )
    session.add(user)
    session.commit()
    return PlatformTokenResponse(access_token=_platform_token(container, user))


@router.post("/auth/login", response_model=PlatformTokenResponse)
def platform_login(
    payload: PlatformCredentials,
    request: Request,
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PlatformTokenResponse:
    limiter = container.auth_rate_limiter
    account = str(payload.email)
    limiter.check_and_hit("platform_ip", client_ip(request))
    limiter.check("platform_account", account)
    user = session.scalar(
        select(PlatformUserModel).where(PlatformUserModel.email == payload.email.lower())
    )
    if (
        user is None
        or user.status != "active"
        or not container.password_hasher.verify(payload.password, user.hashed_password)
    ):
        limiter.hit("platform_account", account)
        raise AuthenticationError("Invalid credentials")
    user.last_login_at = datetime.now(UTC)
    session.commit()
    return PlatformTokenResponse(access_token=_platform_token(container, user))


@router.get("/dashboard", response_model=PlatformDashboardResponse)
def platform_dashboard(
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> PlatformDashboardResponse:
    def count(model: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    return PlatformDashboardResponse(
        total_clients=count(TenantModel),
        active_clients=int(
            session.scalar(select(func.count()).where(TenantModel.status == "active")) or 0
        ),
        inactive_clients=int(
            session.scalar(select(func.count()).where(TenantModel.status == "inactive")) or 0
        ),
        total_users=count(UserModel),
        conversations=count(ConversationModel),
        leads=count(LeadDemandModel),
        properties=count(PropertyModel),
        contacts=count(ContactModel),
        ai_calls=int(
            session.scalar(select(func.count()).where(UsageRecordModel.type == "ai_call")) or 0
        ),
        estimated_ai_cost=session.scalar(
            select(func.coalesce(func.sum(UsageRecordModel.estimated_cost), 0)).where(
                UsageRecordModel.type == "ai_call"
            )
        )
        or Decimal("0"),
        credits_outstanding=int(
            session.scalar(select(func.coalesce(func.sum(CreditAccountModel.balance_credits), 0)))
            or 0
        ),
    )


@router.get("/tenants", response_model=list[PlatformTenantSummary])
def platform_tenants(
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> list[PlatformTenantSummary]:
    tenants = session.scalars(
        select(TenantModel).order_by(TenantModel.created_at.desc()).limit(limit)
    ).all()
    return [_tenant_summary(session, tenant) for tenant in tenants]


@router.get("/tenants/{tenant_id}", response_model=PlatformTenantSummary)
def platform_tenant_detail(
    tenant_id: UUID,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> PlatformTenantSummary:
    tenant = session.get(TenantModel, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    return _tenant_summary(session, tenant)


@router.post("/tenants", response_model=PlatformTenantSummary, status_code=status.HTTP_201_CREATED)
def platform_create_tenant(
    payload: CreateTenantRequest,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> PlatformTenantSummary:
    tenant, _admin = CreateTenantUseCase(
        SqlAlchemyTenantRepository(session), container.password_hasher, container.event_bus
    ).execute(
        payload.name,
        payload.slug,
        payload.admin_name,
        payload.admin_email,
        payload.admin_password,
    )
    model = session.get(TenantModel, tenant.id)
    if model is None:
        raise NotFoundError("Tenant not found")
    return _tenant_summary(session, model)


@router.patch("/tenants/{tenant_id}/status", response_model=PlatformTenantSummary)
def platform_update_tenant_status(
    tenant_id: UUID,
    payload: TenantStatusRequest,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> PlatformTenantSummary:
    tenant = session.get(TenantModel, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    tenant.status = payload.status
    session.commit()
    session.refresh(tenant)
    return _tenant_summary(session, tenant)


@router.post(
    "/tenants/{tenant_id}/credits/grants",
    response_model=PlatformCreditTransaction,
    status_code=status.HTTP_201_CREATED,
)
def platform_grant_credits(
    tenant_id: UUID,
    payload: CreditGrantRequest,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> PlatformCreditTransaction:
    if session.get(TenantModel, tenant_id) is None:
        raise NotFoundError("Tenant not found")
    transaction = CreditLedgerService(session).grant(
        tenant_id,
        payload.credits,
        idempotency_key=payload.idempotency_key,
        description=payload.description,
        created_by=principal.user_id,
    )
    session.commit()
    session.refresh(transaction)
    return PlatformCreditTransaction.from_model(transaction)


@router.patch("/tenants/{tenant_id}/credits/settings", response_model=PlatformTenantSummary)
def platform_update_credit_settings(
    tenant_id: UUID,
    payload: CreditSettingsRequest,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> PlatformTenantSummary:
    tenant = session.get(TenantModel, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    account = CreditLedgerService(session).account(tenant_id)
    account.enforcement_mode = payload.enforcement_mode
    account.unlimited_messages = payload.unlimited_messages
    session.commit()
    return _tenant_summary(session, tenant)


@router.get(
    "/tenants/{tenant_id}/credits/ledger",
    response_model=list[PlatformCreditTransaction],
)
def platform_credit_ledger(
    tenant_id: UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> list[PlatformCreditTransaction]:
    if session.get(TenantModel, tenant_id) is None:
        raise NotFoundError("Tenant not found")
    items = session.scalars(
        select(CreditLedgerModel)
        .where(CreditLedgerModel.tenant_id == tenant_id)
        .order_by(CreditLedgerModel.created_at.desc(), CreditLedgerModel.id.desc())
        .limit(limit)
    ).all()
    return [PlatformCreditTransaction.from_model(item) for item in items]


@router.get("/commercial/plans", response_model=list[CommercialPlanItem])
def platform_commercial_plans(
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> list[CommercialPlanItem]:
    items = session.scalars(
        select(CommercialPlanModel)
        .where(CommercialPlanModel.is_current.is_(True))
        .order_by(CommercialPlanModel.monthly_price_cents, CommercialPlanModel.name)
    ).all()
    return [CommercialPlanItem.model_validate(item, from_attributes=True) for item in items]


@router.get("/commercial/packs", response_model=list[CommercialPackItem])
def platform_commercial_packs(
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> list[CommercialPackItem]:
    items = session.scalars(
        select(CommercialPackModel).order_by(
            CommercialPackModel.resource, CommercialPackModel.units
        )
    ).all()
    return [CommercialPackItem.model_validate(item, from_attributes=True) for item in items]


@router.get("/asaas/status", response_model=AsaasIntegrationStatusResponse)
def platform_asaas_status(
    _: PlatformPrincipal = Depends(get_platform_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> AsaasIntegrationStatusResponse:
    try:
        service = AsaasBillingService(
            session,
            asaas_client_from_settings(container.settings, container.http_client),
            container.settings,
        )
    except ConfigurationError:
        return AsaasIntegrationStatusResponse(configured=False)
    return AsaasIntegrationStatusResponse(**service.account_status())


@router.post(
    "/asaas/webhook",
    response_model=AsaasWebhookProvisionResponse,
    status_code=status.HTTP_201_CREATED,
)
def platform_provision_asaas_webhook(
    payload: AsaasWebhookProvisionRequest,
    _: PlatformPrincipal = Depends(get_platform_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> AsaasWebhookProvisionResponse:
    service = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    )
    webhook = service.provision_webhook(str(payload.notification_email))
    return AsaasWebhookProvisionResponse(
        provider_webhook_id=webhook.provider_webhook_id,
        url=webhook.url,
        enabled=webhook.enabled,
    )


@router.post(
    "/tenants/{tenant_id}/asaas/subscriptions",
    response_model=AsaasSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def platform_create_asaas_subscription(
    tenant_id: UUID,
    payload: AsaasSubscriptionRequest,
    _: PlatformPrincipal = Depends(get_platform_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> AsaasSubscriptionResponse:
    if session.get(TenantModel, tenant_id) is None:
        raise NotFoundError("Tenant not found")
    service = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    )
    subscription = service.create_subscription(
        tenant_id,
        AsaasSubscriptionInput(
            plan_code=payload.plan_code,
            billing_type=payload.billing_type,
            next_due_date=payload.next_due_date,
            enforcement_mode=payload.enforcement_mode,
            idempotency_key=payload.idempotency_key,
            customer=AsaasCustomerInput(
                name=payload.customer.name,
                email=str(payload.customer.email),
                cpf_cnpj=payload.customer.cpf_cnpj,
                mobile_phone=payload.customer.mobile_phone,
                notification_disabled=payload.customer.notification_disabled,
            ),
        ),
    )
    return _asaas_subscription_response(subscription, payload.plan_code)


@router.get(
    "/tenants/{tenant_id}/asaas/subscriptions",
    response_model=list[AsaasSubscriptionResponse],
)
def platform_list_asaas_subscriptions(
    tenant_id: UUID,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> list[AsaasSubscriptionResponse]:
    if session.get(TenantModel, tenant_id) is None:
        raise NotFoundError("Tenant not found")
    rows = session.execute(
        select(AsaasSubscriptionModel, CommercialPlanModel.code)
        .join(CommercialPlanModel, CommercialPlanModel.id == AsaasSubscriptionModel.plan_id)
        .where(AsaasSubscriptionModel.tenant_id == tenant_id)
        .order_by(AsaasSubscriptionModel.created_at.desc())
    ).all()
    return [_asaas_subscription_response(item, plan_code) for item, plan_code in rows]


@router.post(
    "/tenants/{tenant_id}/asaas/subscriptions/{subscription_id}/reconcile",
    response_model=AsaasSubscriptionResponse,
)
def platform_reconcile_asaas_subscription(
    tenant_id: UUID,
    subscription_id: UUID,
    _: PlatformPrincipal = Depends(get_platform_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> AsaasSubscriptionResponse:
    service = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    )
    subscription = service.reconcile_subscription(tenant_id, subscription_id)
    return _asaas_subscription_response(subscription, _plan_code(session, subscription))


@router.post(
    "/tenants/{tenant_id}/asaas/subscriptions/{subscription_id}/cancel",
    response_model=AsaasSubscriptionResponse,
)
def platform_cancel_asaas_subscription(
    tenant_id: UUID,
    subscription_id: UUID,
    _: PlatformPrincipal = Depends(get_platform_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> AsaasSubscriptionResponse:
    service = AsaasBillingService(
        session,
        asaas_client_from_settings(container.settings, container.http_client),
        container.settings,
    )
    subscription = service.cancel_subscription(tenant_id, subscription_id)
    return _asaas_subscription_response(subscription, _plan_code(session, subscription))


def _plan_code(session: Session, subscription: AsaasSubscriptionModel) -> str:
    plan = session.get(CommercialPlanModel, subscription.plan_id)
    return plan.code if plan else ""


def _asaas_subscription_response(
    subscription: AsaasSubscriptionModel, plan_code: str
) -> AsaasSubscriptionResponse:
    return AsaasSubscriptionResponse(
        id=subscription.id,
        provider_customer_id=subscription.provider_customer_id,
        provider_subscription_id=subscription.provider_subscription_id,
        provider_payment_id=subscription.provider_payment_id,
        plan_code=plan_code,
        billing_type=subscription.billing_type,
        value_cents=subscription.value_cents,
        next_due_date=subscription.next_due_date,
        enforcement_mode=subscription.enforcement_mode,
        status=subscription.status,
        invoice_url=subscription.invoice_url,
        last_error=subscription.last_error,
        created_at=subscription.created_at,
    )


@router.put(
    "/tenants/{tenant_id}/commercial-subscription",
    response_model=PlatformTenantSummary,
)
def platform_assign_commercial_plan(
    tenant_id: UUID,
    payload: CommercialSubscriptionRequest,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> PlatformTenantSummary:
    tenant = session.get(TenantModel, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    try:
        CommercialEntitlementService(session).assign_plan(
            tenant_id,
            plan_code=payload.plan_code,
            enforcement_mode=payload.enforcement_mode,
            status=payload.status,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    return _tenant_summary(session, tenant)


@router.post(
    "/tenants/{tenant_id}/commercial-grants",
    response_model=CommercialGrantResponse,
    status_code=status.HTTP_201_CREATED,
)
def platform_grant_commercial_units(
    tenant_id: UUID,
    payload: CommercialGrantRequest,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> CommercialGrantResponse:
    if session.get(TenantModel, tenant_id) is None:
        raise NotFoundError("Tenant not found")
    if payload.resource not in COMMERCIAL_RESOURCES:
        raise NotFoundError("Commercial resource not found")
    item = CommercialEntitlementService(session).grant(
        tenant_id,
        resource=payload.resource,
        quantity=payload.quantity,
        source=payload.source,
        idempotency_key=payload.idempotency_key,
        reference=payload.reference,
        expires_at=payload.expires_at,
        created_by=principal.user_id,
    )
    return CommercialGrantResponse.from_model(item)


@router.post(
    "/tenants/{tenant_id}/commercial-packs",
    response_model=CommercialGrantResponse,
    status_code=status.HTTP_201_CREATED,
)
def platform_grant_commercial_pack(
    tenant_id: UUID,
    payload: CommercialPackGrantRequest,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> CommercialGrantResponse:
    if session.get(TenantModel, tenant_id) is None:
        raise NotFoundError("Tenant not found")
    try:
        item = CommercialEntitlementService(session).grant_pack(
            tenant_id,
            pack_code=payload.pack_code,
            idempotency_key=payload.idempotency_key,
            expires_at=payload.expires_at,
            created_by=principal.user_id,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    return CommercialGrantResponse.from_model(item)


def _tenant_summary(session: Session, tenant: TenantModel) -> PlatformTenantSummary:
    def scoped_count(model: Any) -> int:
        return int(session.scalar(select(func.count()).where(model.tenant_id == tenant.id)) or 0)

    ai_calls = int(
        session.scalar(
            select(func.count()).where(
                UsageRecordModel.tenant_id == tenant.id, UsageRecordModel.type == "ai_call"
            )
        )
        or 0
    )
    cost = session.scalar(
        select(func.coalesce(func.sum(UsageRecordModel.estimated_cost), 0)).where(
            UsageRecordModel.tenant_id == tenant.id, UsageRecordModel.type == "ai_call"
        )
    ) or Decimal("0")
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    integrations = settings.get("integrations", {})
    safe_integrations = {
        str(name): str(value.get("status", "not_configured"))
        for name, value in integrations.items()
        if isinstance(value, dict)
    }
    account = session.get(CreditAccountModel, tenant.id)
    commercial_service = CommercialEntitlementService(session)
    commercial_subscription = commercial_service.subscription(tenant.id)
    session.commit()
    commercial_plan = session.get(CommercialPlanModel, commercial_subscription.plan_id)
    if commercial_plan is None:
        raise RuntimeError("Commercial plan not found")
    commercial_resources = commercial_service.resource_summary(tenant.id)
    return PlatformTenantSummary(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status,
        created_at=tenant.created_at,
        users=scoped_count(UserModel),
        conversations=scoped_count(ConversationModel),
        leads=scoped_count(LeadDemandModel),
        properties=scoped_count(PropertyModel),
        contacts=scoped_count(ContactModel),
        ai_calls=ai_calls,
        estimated_ai_cost=cost,
        credit_balance=account.balance_credits if account else 0,
        credit_reserved=account.reserved_credits if account else 0,
        credit_available=(account.balance_credits - account.reserved_credits if account else 0),
        credit_enforcement=account.enforcement_mode if account else "meter_only",
        unlimited_messages=account.unlimited_messages if account else False,
        commercial_plan=commercial_plan.code,
        commercial_status=commercial_subscription.status,
        commercial_enforcement=commercial_subscription.enforcement_mode,
        commercial_cycle_ends_at=commercial_subscription.cycle_ends_at,
        commercial_available={
            resource: values["available"] for resource, values in commercial_resources.items()
        },
        integrations=safe_integrations,
    )
