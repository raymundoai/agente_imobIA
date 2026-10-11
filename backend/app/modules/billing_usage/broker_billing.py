"""Monthly broker invoices: next month's base price plus unsettled postpaid usage."""

import calendar
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.billing_usage.adapters.models import (
    AsaasCustomerLinkModel,
    AsaasSubscriptionModel,
    BrokerInvoiceModel,
    BrokerInvoiceUsageModel,
    CommercialPlanModel,
    CommercialUsageEventModel,
)
from app.modules.billing_usage.asaas import (
    OPEN_SUBSCRIPTION_STATUSES,
    PAYMENT_PROBLEM_EVENTS,
    PAYMENT_SUCCESS_EVENTS,
    AsaasAmbiguousError,
    AsaasBillingService,
    AsaasClient,
    AsaasCustomerInput,
)
from app.modules.billing_usage.commercial import (
    BROKER_BETA_PLAN_CODE,
    CommercialEntitlementService,
)
from app.shared.errors.exceptions import ConflictError, ExternalServiceError, NotFoundError

BROKER_REFERENCE_PREFIX = "immobia:broker-invoice:"


def next_month(value: datetime) -> datetime:
    year = value.year + (value.month == 12)
    month = value.month % 12 + 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


class BrokerBillingService:
    def __init__(self, session: Session, client: AsaasClient | None, settings: Settings) -> None:
        self._session = session
        self._client = client
        self._settings = settings

    def latest_invoice(self, tenant_id: UUID) -> BrokerInvoiceModel | None:
        return self._session.scalar(
            select(BrokerInvoiceModel)
            .where(BrokerInvoiceModel.tenant_id == tenant_id)
            .order_by(BrokerInvoiceModel.cycle_start.desc())
            .limit(1)
        )

    def create_first_invoice(
        self, tenant_id: UUID, *, billing_type: str, customer: AsaasCustomerInput
    ) -> BrokerInvoiceModel:
        if billing_type not in {"PIX", "CREDIT_CARD"}:
            raise ConflictError("Escolha PIX ou cartão para pagar a mensalidade")
        self._lock(tenant_id)
        commercial = CommercialEntitlementService(self._session).subscription(tenant_id, lock=True)
        if commercial.commercial_segment != "broker" or not commercial.beta_pricing:
            raise ConflictError("A oferta beta está disponível apenas para corretores convidados")
        if commercial.status != "pending":
            raise ConflictError("Esta conta já possui um plano ou pagamento em andamento")
        open_agency = self._session.scalar(
            select(AsaasSubscriptionModel.id).where(
                AsaasSubscriptionModel.tenant_id == tenant_id,
                AsaasSubscriptionModel.status.in_(OPEN_SUBSCRIPTION_STATUSES),
            )
        )
        if open_agency is not None:
            raise ConflictError("Já existe uma assinatura em aberto para esta conta")
        existing = self.latest_invoice(tenant_id)
        if existing is not None:
            if existing.status in {"creating", "failed"}:
                return self._submit(existing)
            return existing
        plan = self._plan()
        provider_customer = AsaasBillingService(
            self._session, self._client, self._settings
        )._ensure_customer(tenant_id, customer)
        now = datetime.now(UTC)
        invoice = self._new_invoice(
            tenant_id=tenant_id,
            plan=plan,
            provider_customer=provider_customer,
            billing_type=billing_type,
            cycle_start=now,
            cycle_end=next_month(now),
            usage=[],
        )
        self._session.commit()
        return self._submit(invoice)

    def create_renewal_invoice(self, tenant_id: UUID) -> BrokerInvoiceModel | None:
        self._lock(tenant_id)
        commercial = CommercialEntitlementService(self._session).subscription(tenant_id, lock=True)
        plan = self._session.get(CommercialPlanModel, commercial.plan_id)
        if plan is None or plan.code != BROKER_BETA_PLAN_CODE:
            return None
        if commercial.status not in {"active", "past_due"}:
            return None
        if commercial.cycle_ends_at > datetime.now(UTC):
            return None
        existing = self._session.scalar(
            select(BrokerInvoiceModel).where(
                BrokerInvoiceModel.tenant_id == tenant_id,
                BrokerInvoiceModel.cycle_start == commercial.cycle_ends_at,
            )
        )
        if existing is not None:
            return self._submit(existing) if existing.status in {"creating", "failed"} else existing
        previous = self.latest_invoice(tenant_id)
        customer = self._session.get(AsaasCustomerLinkModel, tenant_id)
        if previous is None or customer is None:
            raise ConflictError("Dados de cobrança do corretor incompletos")
        events = self.unbilled_usage(tenant_id)
        cycle_start = commercial.cycle_ends_at
        invoice = self._new_invoice(
            tenant_id=tenant_id,
            plan=plan,
            provider_customer=customer,
            billing_type=previous.billing_type,
            cycle_start=cycle_start,
            cycle_end=next_month(cycle_start),
            usage=events,
        )
        self._session.commit()
        return self._submit(invoice)

    def _new_invoice(
        self,
        *,
        tenant_id: UUID,
        plan: CommercialPlanModel,
        provider_customer: AsaasCustomerLinkModel,
        billing_type: str,
        cycle_start: datetime,
        cycle_end: datetime,
        usage: list[CommercialUsageEventModel],
    ) -> BrokerInvoiceModel:
        invoice_id = uuid4()
        charges = sum(int(event.extra["postpaid_unit_cents"]) * event.units for event in usage)
        invoice = BrokerInvoiceModel(
            id=invoice_id,
            tenant_id=tenant_id,
            plan_id=plan.id,
            provider_customer_id=provider_customer.provider_customer_id,
            external_reference=f"{BROKER_REFERENCE_PREFIX}{invoice_id}",
            billing_type=billing_type,
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            due_date=datetime.now(UTC).date() + timedelta(days=3),
            base_cents=plan.monthly_price_cents,
            total_cents=plan.monthly_price_cents + charges,
            status="creating",
        )
        self._session.add(invoice)
        for event in usage:
            self._session.add(
                BrokerInvoiceUsageModel(
                    id=uuid4(),
                    invoice_id=invoice_id,
                    usage_event_id=event.id,
                    resource=event.resource,
                    units=event.units,
                    unit_price_cents=int(event.extra["postpaid_unit_cents"]),
                )
            )
        return invoice

    def unbilled_usage(self, tenant_id: UUID) -> list[CommercialUsageEventModel]:
        events = self._session.scalars(
            select(CommercialUsageEventModel)
            .outerjoin(
                BrokerInvoiceUsageModel,
                BrokerInvoiceUsageModel.usage_event_id == CommercialUsageEventModel.id,
            )
            .where(
                CommercialUsageEventModel.tenant_id == tenant_id,
                CommercialUsageEventModel.grant_id.is_(None),
                BrokerInvoiceUsageModel.id.is_(None),
            )
            .order_by(CommercialUsageEventModel.created_at, CommercialUsageEventModel.id)
        ).all()
        return [
            event
            for event in events
            if isinstance((event.extra or {}).get("postpaid_unit_cents"), int)
            and event.extra["postpaid_unit_cents"] > 0
        ]

    def _submit(self, invoice: BrokerInvoiceModel) -> BrokerInvoiceModel:
        if self._client is None:
            raise ConflictError("Integração de pagamentos indisponível")
        try:
            remote = self._client.find_payment(invoice.external_reference)
            remote = remote or self._client.create_payment(
                {
                    "customer": invoice.provider_customer_id,
                    "billingType": invoice.billing_type,
                    "value": invoice.total_cents / 100,
                    "dueDate": invoice.due_date.isoformat(),
                    "description": "ImmobIA · mensalidade e consumo do corretor",
                    "externalReference": invoice.external_reference,
                }
            )
        except AsaasAmbiguousError:
            self._session.commit()
            raise
        except ExternalServiceError as exc:
            invoice.status = "failed"
            invoice.last_error = str(exc)
            self._session.commit()
            raise
        self._session.refresh(invoice)
        invoice.provider_payment_id = str(remote["id"])
        invoice.invoice_url = remote.get("invoiceUrl")
        if invoice.status not in {"paid", "past_due"}:
            invoice.status = "pending_payment"
        invoice.last_error = None
        self._session.commit()
        return invoice

    def invoice_for_payment(self, payment: dict) -> BrokerInvoiceModel | None:
        reference = payment.get("externalReference")
        provider_id = payment.get("id")
        if isinstance(reference, str) and reference.startswith(BROKER_REFERENCE_PREFIX):
            return self._session.scalar(
                select(BrokerInvoiceModel)
                .where(BrokerInvoiceModel.external_reference == reference)
                .with_for_update()
            )
        if isinstance(provider_id, str):
            return self._session.scalar(
                select(BrokerInvoiceModel)
                .where(BrokerInvoiceModel.provider_payment_id == provider_id)
                .with_for_update()
            )
        return None

    def settle_event(self, invoice: BrokerInvoiceModel, event_type: str, payment: dict) -> str:
        if payment.get("value") is not None:
            paid_cents = round(Decimal(str(payment["value"])) * 100)
            if paid_cents != invoice.total_cents:
                raise ConflictError("Valor da fatura diverge do pagamento informado pelo Asaas")
        if payment.get("customer") and payment["customer"] != invoice.provider_customer_id:
            raise ConflictError("Cliente da fatura diverge do pagamento informado pelo Asaas")
        invoice.provider_payment_id = payment.get("id") or invoice.provider_payment_id
        invoice.invoice_url = payment.get("invoiceUrl") or invoice.invoice_url
        if event_type in PAYMENT_SUCCESS_EVENTS:
            if invoice.status == "paid":
                return "already_paid"
            invoice.status = "paid"
            invoice.paid_at = datetime.now(UTC)
            plan = self._session.get(CommercialPlanModel, invoice.plan_id)
            if plan is None:
                raise RuntimeError("Plano da fatura não encontrado")
            current = CommercialEntitlementService(self._session).subscription(invoice.tenant_id)
            if current.status == "pending":
                # The first full month starts when payment actually clears.
                invoice.cycle_start = invoice.paid_at
                invoice.cycle_end = next_month(invoice.paid_at)
            CommercialEntitlementService(self._session).assign_plan(
                invoice.tenant_id,
                plan_code=plan.code,
                enforcement_mode="enforce",
                status="active",
                cycle_start=invoice.cycle_start,
                cycle_end=invoice.cycle_end,
            )
            return "broker_invoice_paid"
        if event_type in PAYMENT_PROBLEM_EVENTS:
            if invoice.status != "paid":
                invoice.status = "past_due"
            else:
                CommercialEntitlementService(self._session).suspend(
                    invoice.tenant_id, status="past_due", expire_plan_grants=False, commit=False
                )
            return "broker_invoice_past_due"
        return "broker_invoice_recorded"

    def pix_for_invoice(self, tenant_id: UUID) -> dict:
        if self._client is None:
            raise ConflictError("Integração de pagamentos indisponível")
        invoice = self.latest_invoice(tenant_id)
        if invoice is None or invoice.status not in {"pending_payment", "past_due"}:
            raise NotFoundError("Não há mensalidade em aberto")
        if invoice.billing_type != "PIX" or invoice.provider_payment_id is None:
            raise ConflictError("Esta fatura não é paga por PIX")
        return self._client.pix_qr_code(invoice.provider_payment_id)

    def _plan(self) -> CommercialPlanModel:
        plan = self._session.scalar(
            select(CommercialPlanModel).where(
                CommercialPlanModel.code == BROKER_BETA_PLAN_CODE,
                CommercialPlanModel.is_current.is_(True),
            )
        )
        if plan is None:
            raise ConflictError("Plano beta de corretor indisponível")
        return plan

    def _lock(self, tenant_id: UUID) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"broker-invoice:{tenant_id}"},
        )
