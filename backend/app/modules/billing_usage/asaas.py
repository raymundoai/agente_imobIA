"""Asaas billing adapter and local reconciliation service."""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.billing_usage.adapters.models import (
    AsaasCustomerLinkModel,
    AsaasPackOrderModel,
    AsaasSubscriptionModel,
    AsaasWebhookConfigModel,
    AsaasWebhookEventModel,
    CommercialPlanModel,
)
from app.modules.billing_usage.commercial import (
    PACK_VALIDITY_DAYS,
    CommercialEntitlementService,
    effective_price_cents,
    is_internal_test_plan,
    pack_offers,
)
from app.shared.errors.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
)

PAYMENT_EVENTS = [
    "PAYMENT_CREATED",
    "PAYMENT_CONFIRMED",
    "PAYMENT_RECEIVED",
    "PAYMENT_OVERDUE",
    "PAYMENT_DELETED",
    "PAYMENT_REFUNDED",
]
SUBSCRIPTION_EVENTS = ["SUBSCRIPTION_INACTIVATED", "SUBSCRIPTION_DELETED"]
WEBHOOK_EVENTS = PAYMENT_EVENTS + SUBSCRIPTION_EVENTS
PAYMENT_SUCCESS_EVENTS = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}
PAYMENT_PROBLEM_EVENTS = {"PAYMENT_OVERDUE", "PAYMENT_REFUNDED"}
SUBSCRIPTION_END_EVENTS = set(SUBSCRIPTION_EVENTS)
# Statuses that still bill (or may bill) the customer in Asaas. A tenant can have only one.
OPEN_SUBSCRIPTION_STATUSES = ("creating", "pending_payment", "active", "past_due")
EXTERNAL_REFERENCE_PREFIX = "immobia:subscription:"
PACK_REFERENCE_PREFIX = "immobia:pack:"


class AsaasAmbiguousError(ExternalServiceError):
    """The request may or may not have been applied by Asaas (transport error or 5xx)."""


class AsaasClient:
    """Small, explicit wrapper around the Asaas v3 API."""

    def __init__(self, http_client: httpx.Client, *, base_url: str, api_key: str) -> None:
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def account(self) -> dict[str, Any]:
        return self._request("GET", "/myAccount")

    def find_customer(self, external_reference: str) -> dict[str, Any] | None:
        payload = self._request(
            "GET", "/customers", params={"externalReference": external_reference, "limit": 1}
        )
        return _first_item(payload)

    def create_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/customers", json=payload)

    def create_subscription(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/subscriptions", json=payload)

    def find_subscription(self, external_reference: str) -> dict[str, Any] | None:
        payload = self._request(
            "GET",
            "/subscriptions",
            params={"externalReference": external_reference, "includeDeleted": "true", "limit": 1},
        )
        return _first_item(payload)

    def delete_subscription(self, subscription_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/subscriptions/{subscription_id}")

    def subscription_payments(self, subscription_id: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/subscriptions/{subscription_id}/payments")
        items = payload.get("data")
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def create_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/payments", json=payload)

    def find_payment(self, external_reference: str) -> dict[str, Any] | None:
        payload = self._request(
            "GET", "/payments", params={"externalReference": external_reference, "limit": 1}
        )
        return _first_item(payload)

    def pix_qr_code(self, payment_id: str) -> dict[str, Any]:
        return self._request("GET", f"/payments/{payment_id}/pixQrCode")

    def create_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/webhooks", json=payload)

    def update_webhook(self, webhook_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/webhooks/{webhook_id}", json=payload)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http_client.request(
                method,
                f"{self._base_url}{path}",
                headers={"access_token": self._api_key},
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise AsaasAmbiguousError("Não foi possível alcançar a API do Asaas") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 500:
            raise AsaasAmbiguousError(
                f"Asaas retornou status {response.status_code}: {_provider_detail(payload)}"
            )
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Asaas retornou status {response.status_code}: {_provider_detail(payload)}"
            )
        if not isinstance(payload, dict):
            raise ExternalServiceError("Asaas retornou uma resposta inválida")
        return payload


@dataclass(frozen=True, slots=True)
class AsaasCustomerInput:
    name: str
    email: str
    cpf_cnpj: str
    mobile_phone: str | None = None
    notification_disabled: bool = True


@dataclass(frozen=True, slots=True)
class AsaasSubscriptionInput:
    plan_code: str
    billing_type: str
    next_due_date: date
    enforcement_mode: str
    idempotency_key: str
    customer: AsaasCustomerInput


@dataclass(frozen=True, slots=True)
class AsaasWebhookResult:
    duplicate: bool
    outcome: str
    subscription_id: UUID | None


def asaas_client_from_settings(settings: Settings, http_client: httpx.Client) -> AsaasClient:
    if settings.asaas_api_base_url is None or settings.asaas_api_key is None:
        raise ConfigurationError("Integração Asaas ainda não configurada no backend")
    return AsaasClient(
        http_client,
        base_url=str(settings.asaas_api_base_url),
        api_key=settings.asaas_api_key.get_secret_value(),
    )


def asaas_webhook_token(settings: Settings) -> str:
    """Return the webhook token, never the Asaas API key.

    A dedicated ASAAS_WEBHOOK_TOKEN survives rotation of the other secrets. Without it the
    token is derived, so rotating INTEGRATION_SECRET_KEY requires provisioning the webhook again.
    """

    if settings.asaas_webhook_token is not None:
        token = settings.asaas_webhook_token.get_secret_value()
        if len(token) < 32:
            raise ConfigurationError("ASAAS_WEBHOOK_TOKEN deve ter pelo menos 32 caracteres")
        return token
    seed = (
        settings.integration_secret_key.get_secret_value()
        if settings.integration_secret_key is not None
        else settings.jwt_secret.get_secret_value()
    )
    return hmac.new(seed.encode(), b"immobia:asaas-webhook:v1", hashlib.sha256).hexdigest()


def asaas_webhook_url(settings: Settings) -> str:
    if settings.backend_public_url is None:
        raise ConfigurationError("BACKEND_PUBLIC_URL é necessária para configurar o webhook Asaas")
    return f"{str(settings.backend_public_url).rstrip('/')}/webhooks/asaas"


class AsaasBillingService:
    def __init__(self, session: Session, client: AsaasClient, settings: Settings) -> None:
        self._session = session
        self._client = client
        self._settings = settings

    def account_status(self) -> dict[str, Any]:
        account = self._client.account()
        environment_url = str(self._settings.asaas_api_base_url)
        webhook = self._session.scalar(
            select(AsaasWebhookConfigModel).where(
                AsaasWebhookConfigModel.environment_url == environment_url
            )
        )
        try:
            expected_webhook_url: str | None = asaas_webhook_url(self._settings)
        except ConfigurationError:
            expected_webhook_url = None
        return {
            "configured": True,
            "environment_url": environment_url,
            "account_id": _string(account.get("id")),
            "account_name": _string(account.get("name")),
            "webhook_url": webhook.url if webhook else None,
            "webhook_notification_email": webhook.notification_email if webhook else None,
            "expected_webhook_url": expected_webhook_url,
        }

    def create_subscription(
        self, tenant_id: UUID, request: AsaasSubscriptionInput
    ) -> AsaasSubscriptionModel:
        # Serializes creation per tenant until the "creating" row below is committed.
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"asaas-subscription:{tenant_id}"},
        )
        existing = self._session.scalar(
            select(AsaasSubscriptionModel)
            .where(
                AsaasSubscriptionModel.tenant_id == tenant_id,
                AsaasSubscriptionModel.idempotency_key == request.idempotency_key,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.provider_subscription_id or existing.status != "creating":
                if existing.status == "failed":
                    raise ConflictError(
                        f"O Asaas recusou a tentativa anterior: {existing.last_error}. "
                        "Corrija os dados e tente novamente."
                    )
                return existing
            return self._resume(existing)
        open_subscription = self._session.scalar(
            select(AsaasSubscriptionModel).where(
                AsaasSubscriptionModel.tenant_id == tenant_id,
                AsaasSubscriptionModel.status.in_(OPEN_SUBSCRIPTION_STATUSES),
            )
        )
        if open_subscription is not None:
            raise ConflictError(
                "Este cliente já possui uma assinatura Asaas em aberto "
                f"({open_subscription.status}). Cancele ou reconcilie a atual antes de criar outra."
            )
        plan = self._session.scalar(
            select(CommercialPlanModel).where(
                CommercialPlanModel.code == request.plan_code,
                CommercialPlanModel.is_current.is_(True),
            )
        )
        commercial = CommercialEntitlementService(self._session).subscription(tenant_id)
        offered = plan is not None and (
            plan.is_public if not commercial.internal_test else is_internal_test_plan(plan)
        )
        if plan is None or not offered:
            raise ConflictError("Plano comercial indisponível para cobrança")
        if plan.monthly_price_cents <= 0:
            raise ConflictError("O plano precisa ter preço mensal definido antes da cobrança")
        beta = commercial.beta_pricing and not commercial.internal_test
        customer = self._ensure_customer(tenant_id, request.customer)
        local_id = uuid4()
        subscription = AsaasSubscriptionModel(
            id=local_id,
            tenant_id=tenant_id,
            plan_id=plan.id,
            provider_customer_id=customer.provider_customer_id,
            external_reference=f"{EXTERNAL_REFERENCE_PREFIX}{local_id}",
            idempotency_key=request.idempotency_key,
            billing_type=request.billing_type,
            value_cents=effective_price_cents(plan, beta=beta),
            next_due_date=request.next_due_date,
            enforcement_mode=request.enforcement_mode,
            status="creating",
        )
        self._session.add(subscription)
        self._session.commit()
        return self._submit(subscription)

    def reconcile_subscription(
        self, tenant_id: UUID, subscription_id: UUID
    ) -> AsaasSubscriptionModel:
        subscription = self._locked_subscription(tenant_id, subscription_id)
        if subscription.status != "creating" or subscription.provider_subscription_id:
            return subscription
        return self._resume(subscription)

    def cancel_subscription(self, tenant_id: UUID, subscription_id: UUID) -> AsaasSubscriptionModel:
        subscription = self._locked_subscription(tenant_id, subscription_id)
        if subscription.status in {"cancelled", "failed"}:
            return subscription
        if not subscription.provider_subscription_id:
            remote = self._find_remote(subscription)
            if remote is not None:
                self._adopt(subscription, remote)
        if subscription.provider_subscription_id:
            self._client.delete_subscription(subscription.provider_subscription_id)
        self._end_subscription(subscription, extra_event="cancelled_by_platform")
        self._session.commit()
        return subscription

    def pix_for_open_charge(self, tenant_id: UUID) -> dict[str, Any]:
        """QR code of the tenant's oldest unpaid PIX charge, shown inside the app."""

        subscription = self._session.scalar(
            select(AsaasSubscriptionModel)
            .where(
                AsaasSubscriptionModel.tenant_id == tenant_id,
                AsaasSubscriptionModel.status.in_(("pending_payment", "past_due")),
                AsaasSubscriptionModel.provider_subscription_id.is_not(None),
            )
            .order_by(AsaasSubscriptionModel.created_at.desc())
        )
        if subscription is None or subscription.provider_subscription_id is None:
            raise NotFoundError("Não há cobrança em aberto para pagar")
        if subscription.billing_type != "PIX":
            raise ConflictError("Esta assinatura é paga com cartão de crédito")
        unpaid = [
            payment
            for payment in self._client.subscription_payments(subscription.provider_subscription_id)
            if payment.get("status") in {"PENDING", "OVERDUE"} and _string(payment.get("id"))
        ]
        if not unpaid:
            raise NotFoundError("Não há cobrança em aberto para pagar")
        payment = min(unpaid, key=lambda item: str(item.get("dueDate") or ""))
        qr_code = self._client.pix_qr_code(str(payment["id"]))
        if not _string(qr_code.get("payload")) or not _string(qr_code.get("encodedImage")):
            raise ExternalServiceError("Asaas não retornou o QR Code do PIX")
        return {
            "payment_id": payment["id"],
            "value": payment.get("value"),
            "due_date": payment.get("dueDate"),
            "payload": qr_code["payload"],
            "encoded_image": qr_code["encodedImage"],
            "expiration_date": qr_code.get("expirationDate"),
        }

    def create_pack_order(
        self, tenant_id: UUID, *, resource: str, idempotency_key: str
    ) -> AsaasPackOrderModel:
        """One-off charge for an extra-allowance pack of the tenant's current plan."""

        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"asaas-pack:{tenant_id}"},
        )
        existing = self._session.scalar(
            select(AsaasPackOrderModel)
            .where(
                AsaasPackOrderModel.tenant_id == tenant_id,
                AsaasPackOrderModel.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if existing is not None:
            return existing if existing.status != "creating" else self._submit_pack(existing)
        commercial = CommercialEntitlementService(self._session).subscription(tenant_id)
        plan = self._session.get(CommercialPlanModel, commercial.plan_id)
        if plan is None or commercial.status not in {"active", "past_due"} or not plan.is_public:
            raise ConflictError("Assine um plano antes de comprar pacotes adicionais")
        offer = next((item for item in pack_offers(plan) if item["resource"] == resource), None)
        if offer is None:
            raise ConflictError("Este pacote não está disponível no seu plano")
        customer = self._session.get(AsaasCustomerLinkModel, tenant_id)
        if customer is None:
            raise ConflictError("Assine um plano antes de comprar pacotes adicionais")
        local_id = uuid4()
        order = AsaasPackOrderModel(
            id=local_id,
            tenant_id=tenant_id,
            resource=resource,
            units=int(offer["units"]),
            value_cents=int(offer["price_cents"]),
            plan_code=plan.code,
            idempotency_key=idempotency_key,
            external_reference=f"{PACK_REFERENCE_PREFIX}{local_id}",
            status="creating",
        )
        self._session.add(order)
        self._session.commit()
        return self._submit_pack(order)

    def pix_for_pack_order(self, tenant_id: UUID, order_id: UUID) -> dict[str, Any]:
        order = self._session.scalar(
            select(AsaasPackOrderModel).where(
                AsaasPackOrderModel.id == order_id, AsaasPackOrderModel.tenant_id == tenant_id
            )
        )
        if order is None or order.provider_payment_id is None:
            raise NotFoundError("Pedido de pacote não encontrado")
        if order.status != "pending_payment":
            raise ConflictError("Este pedido não está aguardando pagamento")
        qr_code = self._client.pix_qr_code(order.provider_payment_id)
        if not _string(qr_code.get("payload")) or not _string(qr_code.get("encodedImage")):
            raise ExternalServiceError("Asaas não retornou o QR Code do PIX")
        return {
            "payment_id": order.provider_payment_id,
            "value": order.value_cents / 100,
            "due_date": None,
            "payload": qr_code["payload"],
            "encoded_image": qr_code["encodedImage"],
            "expiration_date": qr_code.get("expirationDate"),
        }

    def _submit_pack(self, order: AsaasPackOrderModel) -> AsaasPackOrderModel:
        customer = self._session.get(AsaasCustomerLinkModel, order.tenant_id)
        if customer is None:
            raise ConflictError("Cliente Asaas não encontrado para este pedido")
        try:
            # A retry after a lost response finds the charge instead of creating a second one.
            remote = self._client.find_payment(order.external_reference)
            remote = remote or self._client.create_payment(
                {
                    "customer": customer.provider_customer_id,
                    "billingType": "UNDEFINED",
                    "value": order.value_cents / 100,
                    "dueDate": (datetime.now(UTC) + timedelta(days=3)).date().isoformat(),
                    "description": f"ImmobIA · pacote de {order.units} unidades",
                    "externalReference": order.external_reference,
                }
            )
        except AsaasAmbiguousError:
            raise
        except ExternalServiceError as exc:
            order.status = "failed"
            order.last_error = str(exc)
            self._session.commit()
            raise
        order.provider_payment_id = _required_id(remote, "cobrança")
        order.invoice_url = _string(remote.get("invoiceUrl"))
        order.status = "pending_payment"
        self._session.commit()
        return order

    def _pack_order_for_event(self, payment: dict[str, Any]) -> AsaasPackOrderModel | None:
        reference = _string(payment.get("externalReference"))
        payment_id = _string(payment.get("id"))
        if reference and reference.startswith(PACK_REFERENCE_PREFIX):
            return self._session.scalar(
                select(AsaasPackOrderModel)
                .where(AsaasPackOrderModel.external_reference == reference)
                .with_for_update()
            )
        if payment_id:
            return self._session.scalar(
                select(AsaasPackOrderModel)
                .where(AsaasPackOrderModel.provider_payment_id == payment_id)
                .with_for_update()
            )
        return None

    def _settle_pack(self, order: AsaasPackOrderModel, event_type: str) -> str:
        if event_type in PAYMENT_SUCCESS_EVENTS:
            if order.status == "paid":
                return "pack_already_paid"
            now = datetime.now(UTC)
            # Marked first: grant() commits, and the order must never look unpaid once credited.
            order.status = "paid"
            order.paid_at = now
            grant = CommercialEntitlementService(self._session).grant(
                order.tenant_id,
                resource=order.resource,
                quantity=order.units,
                source="pack",
                idempotency_key=f"pack-order:{order.id}",
                reference=order.plan_code,
                expires_at=now + timedelta(days=PACK_VALIDITY_DAYS),
                created_by=None,
                extra={"pack_order_id": str(order.id)},
            )
            order.grant_id = grant.id
            return "pack_granted"
        if event_type in PAYMENT_PROBLEM_EVENTS and order.status != "paid":
            order.status = "cancelled"
            return "pack_cancelled"
        return "recorded"

    def provision_webhook(self, notification_email: str) -> AsaasWebhookConfigModel:
        url = asaas_webhook_url(self._settings)
        token = asaas_webhook_token(self._settings)
        payload = {
            "name": "ImmobIA billing",
            "url": url,
            "email": notification_email,
            "enabled": True,
            "interrupted": False,
            "apiVersion": 3,
            "authToken": token,
            "sendType": "SEQUENTIALLY",
            "events": WEBHOOK_EVENTS,
        }
        environment_url = str(self._settings.asaas_api_base_url)
        config = self._session.scalar(
            select(AsaasWebhookConfigModel)
            .where(AsaasWebhookConfigModel.environment_url == environment_url)
            .with_for_update()
        )
        if config is None:
            response = self._client.create_webhook(payload)
            config = AsaasWebhookConfigModel(
                id=uuid4(),
                environment_url=environment_url,
                provider_webhook_id=_required_id(response, "webhook"),
                url=url,
                notification_email=notification_email,
                enabled=True,
            )
            self._session.add(config)
        else:
            self._client.update_webhook(config.provider_webhook_id, payload)
            config.url = url
            config.notification_email = notification_email
            config.enabled = True
        self._session.commit()
        return config

    def process_webhook(self, payload: dict[str, Any]) -> AsaasWebhookResult:
        event_id = _string(payload.get("id"))
        event_type = _string(payload.get("event"))
        if not event_id or not event_type:
            raise ConflictError("Evento do Asaas sem identificador ou tipo")
        duplicate = self._session.scalar(
            select(AsaasWebhookEventModel.id).where(
                AsaasWebhookEventModel.provider_event_id == event_id
            )
        )
        if duplicate is not None:
            return AsaasWebhookResult(duplicate=True, outcome="duplicate", subscription_id=None)

        payment = _dict(payload.get("payment"))
        pack_order = self._pack_order_for_event(payment) if payment else None
        if pack_order is not None:
            event = AsaasWebhookEventModel(
                id=uuid4(),
                provider_event_id=event_id,
                event_type=event_type,
                subscription_id=None,
                payload=payload,
                outcome="recorded",
                processed_at=datetime.now(UTC),
            )
            self._session.add(event)
            event.outcome = self._settle_pack(pack_order, event_type)
            self._session.commit()
            return AsaasWebhookResult(duplicate=False, outcome=event.outcome, subscription_id=None)
        subscription = self._subscription_for_event(payment, _dict(payload.get("subscription")))
        event = AsaasWebhookEventModel(
            id=uuid4(),
            provider_event_id=event_id,
            event_type=event_type,
            subscription_id=subscription.id if subscription else None,
            payload=payload,
            outcome="ignored" if subscription is None else "recorded",
            processed_at=datetime.now(UTC),
        )
        self._session.add(event)
        if subscription is None:
            self._session.commit()
            return AsaasWebhookResult(duplicate=False, outcome="ignored", subscription_id=None)

        if payment:
            subscription.provider_payment_id = (
                _string(payment.get("id")) or subscription.provider_payment_id
            )
            subscription.invoice_url = (
                _string(payment.get("invoiceUrl")) or subscription.invoice_url
            )
        extra = dict(subscription.extra or {})
        if payment:
            extra["last_payment_status"] = _string(payment.get("status"))
        extra["last_event"] = event_type
        subscription.extra = extra

        if event_type in PAYMENT_SUCCESS_EVENTS:
            event.outcome = self._activate(subscription)
        elif event_type in PAYMENT_PROBLEM_EVENTS:
            event.outcome = self._mark_past_due(subscription)
        elif event_type in SUBSCRIPTION_END_EVENTS:
            event.outcome = (
                "cancelled_recorded" if subscription.status != "cancelled" else "already_cancelled"
            )
            self._end_subscription(subscription, extra_event=event_type)
        self._session.commit()
        return AsaasWebhookResult(
            duplicate=False, outcome=event.outcome, subscription_id=subscription.id
        )

    def _activate(self, subscription: AsaasSubscriptionModel) -> str:
        if subscription.status in {"cancelled", "failed"}:
            # A late confirmation must not revive a subscription that was ended.
            return "ignored_inactive_subscription"
        subscription.status = "active"
        plan = self._session.get(CommercialPlanModel, subscription.plan_id)
        if plan is None:
            raise RuntimeError("Plano comercial da assinatura Asaas não encontrado")
        self._session.flush()
        CommercialEntitlementService(self._session).assign_plan(
            subscription.tenant_id,
            plan_code=plan.code,
            enforcement_mode=subscription.enforcement_mode,
            status="active",
        )
        return "activated"

    def _mark_past_due(self, subscription: AsaasSubscriptionModel) -> str:
        if subscription.status in {"cancelled", "failed"}:
            return "ignored_inactive_subscription"
        was_paying = subscription.status in {"active", "past_due"}
        subscription.status = "past_due"
        if not was_paying or not self._tenant_runs_on(subscription):
            # Never paid, or the tenant is on another plan: nothing to suspend.
            return "past_due_recorded"
        CommercialEntitlementService(self._session).suspend(
            subscription.tenant_id, status="past_due", expire_plan_grants=False, commit=False
        )
        return "past_due_suspended"

    def _end_subscription(self, subscription: AsaasSubscriptionModel, *, extra_event: str) -> None:
        if subscription.status == "cancelled":
            return
        was_paying = subscription.status in {"active", "past_due"}
        subscription.status = "cancelled"
        extra = dict(subscription.extra or {})
        extra["ended_by"] = extra_event
        subscription.extra = extra
        if was_paying and self._tenant_runs_on(subscription):
            CommercialEntitlementService(self._session).suspend(
                subscription.tenant_id, status="cancelled", expire_plan_grants=True, commit=False
            )

    def _tenant_runs_on(self, subscription: AsaasSubscriptionModel) -> bool:
        """Whether the tenant's commercial plan still comes from this Asaas subscription."""

        tenant_subscription = CommercialEntitlementService(self._session).subscription(
            subscription.tenant_id, lock=True
        )
        return tenant_subscription.plan_id == subscription.plan_id and (
            tenant_subscription.status in {"active", "past_due"}
        )

    def _subscription_for_event(
        self, payment: dict[str, Any], subscription_payload: dict[str, Any]
    ) -> AsaasSubscriptionModel | None:
        provider_subscription_id = _string(payment.get("subscription")) or _string(
            subscription_payload.get("id")
        )
        if provider_subscription_id:
            found = self._session.scalar(
                select(AsaasSubscriptionModel)
                .where(AsaasSubscriptionModel.provider_subscription_id == provider_subscription_id)
                .with_for_update()
            )
            if found is not None:
                return found
        external_reference = _string(subscription_payload.get("externalReference")) or _string(
            payment.get("externalReference")
        )
        if not external_reference or not external_reference.startswith(EXTERNAL_REFERENCE_PREFIX):
            return None
        found = self._session.scalar(
            select(AsaasSubscriptionModel)
            .where(AsaasSubscriptionModel.external_reference == external_reference)
            .with_for_update()
        )
        if found is not None and not found.provider_subscription_id and provider_subscription_id:
            # The webhook arrived before the creation response was stored.
            found.provider_subscription_id = provider_subscription_id
            if found.status == "creating":
                found.status = "pending_payment"
        return found

    def _resume(self, subscription: AsaasSubscriptionModel) -> AsaasSubscriptionModel:
        """Finish a creation whose outcome is unknown without creating a second subscription."""

        try:
            remote = self._find_remote(subscription)
        except AsaasAmbiguousError:
            self._session.commit()
            raise
        if remote is not None:
            self._adopt(subscription, remote)
            self._session.commit()
            return subscription
        return self._submit(subscription)

    def _submit(self, subscription: AsaasSubscriptionModel) -> AsaasSubscriptionModel:
        plan = self._session.get(CommercialPlanModel, subscription.plan_id)
        if plan is None:
            raise RuntimeError("Plano comercial da assinatura Asaas não encontrado")
        try:
            created = self._client.create_subscription(
                {
                    "customer": subscription.provider_customer_id,
                    "billingType": subscription.billing_type,
                    "value": subscription.value_cents / 100,
                    "nextDueDate": subscription.next_due_date.isoformat(),
                    "cycle": "MONTHLY",
                    "description": f"ImmobIA — {plan.name}",
                    "externalReference": subscription.external_reference,
                }
            )
        except AsaasAmbiguousError as exc:
            # The subscription may exist in Asaas. Keep it as "creating" so a retry reconciles
            # by externalReference instead of billing the customer twice.
            subscription.last_error = str(exc)
            try:
                remote = self._find_remote(subscription)
            except ExternalServiceError:
                remote = None
            if remote is None:
                self._session.commit()
                raise AsaasAmbiguousError(
                    "Não foi possível confirmar a criação da assinatura no Asaas. "
                    "Use “Reconciliar” antes de tentar outra vez."
                ) from exc
            created = remote
        except ExternalServiceError as exc:
            subscription.status = "failed"
            subscription.last_error = str(exc)
            self._session.commit()
            raise
        self._adopt(subscription, created)
        self._session.commit()
        return subscription

    def _adopt(self, subscription: AsaasSubscriptionModel, remote: dict[str, Any]) -> None:
        subscription.provider_subscription_id = _required_id(remote, "assinatura")
        subscription.last_error = None
        extra = dict(subscription.extra or {})
        extra["provider_status"] = remote.get("status")
        subscription.extra = extra
        if remote.get("deleted") is True:
            subscription.status = "cancelled"
            return
        if subscription.status == "creating":
            subscription.status = "pending_payment"
        try:
            self._set_initial_payment(subscription)
        except ExternalServiceError:
            # The invoice link also arrives with PAYMENT_CREATED; it is not worth failing for.
            pass

    def _find_remote(self, subscription: AsaasSubscriptionModel) -> dict[str, Any] | None:
        return self._client.find_subscription(subscription.external_reference)

    def _locked_subscription(
        self, tenant_id: UUID, subscription_id: UUID
    ) -> AsaasSubscriptionModel:
        subscription = self._session.scalar(
            select(AsaasSubscriptionModel)
            .where(
                AsaasSubscriptionModel.id == subscription_id,
                AsaasSubscriptionModel.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if subscription is None:
            raise NotFoundError("Assinatura Asaas não encontrada")
        return subscription

    def _ensure_customer(
        self, tenant_id: UUID, customer: AsaasCustomerInput
    ) -> AsaasCustomerLinkModel:
        existing = self._session.get(AsaasCustomerLinkModel, tenant_id)
        if existing is not None:
            return existing
        external_reference = f"immobia:tenant:{tenant_id}"
        provider_customer = self._client.find_customer(external_reference)
        if provider_customer is None:
            provider_customer = self._client.create_customer(
                {
                    "name": customer.name,
                    "email": customer.email,
                    "cpfCnpj": customer.cpf_cnpj,
                    "mobilePhone": customer.mobile_phone,
                    "externalReference": external_reference,
                    "notificationDisabled": customer.notification_disabled,
                }
            )
        link = AsaasCustomerLinkModel(
            tenant_id=tenant_id,
            provider_customer_id=_required_id(provider_customer, "cliente"),
        )
        self._session.add(link)
        # Flushed, not committed: the tenant lock must last until the subscription row exists.
        self._session.flush()
        return link

    def _set_initial_payment(self, subscription: AsaasSubscriptionModel) -> None:
        if not subscription.provider_subscription_id:
            return
        payments = self._client.subscription_payments(subscription.provider_subscription_id)
        if not payments:
            return
        first_payment = payments[0]
        subscription.provider_payment_id = _string(first_payment.get("id"))
        subscription.invoice_url = _string(first_payment.get("invoiceUrl"))


def verify_asaas_webhook_token(settings: Settings, supplied_token: str | None) -> None:
    expected_token = asaas_webhook_token(settings)
    if supplied_token is None or not hmac.compare_digest(supplied_token, expected_token):
        raise AuthenticationError("Token de webhook Asaas inválido")


def _required_id(payload: dict[str, Any], resource: str) -> str:
    identifier = _string(payload.get("id"))
    if not identifier:
        raise ExternalServiceError(f"Asaas não retornou identificador do {resource}")
    return identifier


def _first_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    items = payload.get("data")
    if not isinstance(items, list) or not items:
        return None
    return items[0] if isinstance(items[0], dict) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _provider_detail(payload: Any) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list):
            messages = [
                _string(item.get("description")) for item in errors if isinstance(item, dict)
            ]
            if any(messages):
                return "; ".join(message for message in messages if message)
        for key in ("description", "message"):
            detail = _string(payload.get(key))
            if detail:
                return detail
    return "erro sem detalhe"
