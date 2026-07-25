from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.billing_usage.adapters.models import (
    CreditAccountModel,
    CreditLedgerModel,
    CreditReservationModel,
)
from app.shared.errors.exceptions import PaymentRequiredError

CREDIT_VALUE_USD = Decimal("0.001")
DEFAULT_MARKUP_MULTIPLIER = Decimal("2.0")
PRICING_CATALOG_VERSION = "2026-07-25"

CHAT_RATES_USD_PER_MILLION: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "gpt-5-nano": (Decimal("0.05"), Decimal("0.005"), Decimal("0.40")),
    "gpt-5.5": (Decimal("5.00"), Decimal("0.50"), Decimal("30.00")),
    "gpt-5.4-mini": (Decimal("0.75"), Decimal("0.075"), Decimal("4.50")),
}
IMAGE_TOKEN_RATES_USD_PER_MILLION: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "gpt-image-2": (Decimal("8.00"), Decimal("5.00"), Decimal("30.00")),
}


@dataclass(frozen=True, slots=True)
class CreditCharge:
    provider_cost_usd: Decimal
    retail_cost_usd: Decimal
    credits: int


class CreditReservationClosed(RuntimeError):
    pass


def estimated_chat_charge(model: str) -> CreditCharge:
    return chat_charge(
        model,
        input_tokens=100_000,
        cached_input_tokens=0,
        output_tokens=10_000,
    )


def estimated_image_charge(model: str) -> CreditCharge:
    return image_token_charge(
        model,
        input_image_tokens=20_000,
        input_text_tokens=1_000,
        output_image_tokens=20_000,
    )


def chat_charge(
    model: str,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    markup_multiplier: Decimal = DEFAULT_MARKUP_MULTIPLIER,
) -> CreditCharge:
    rates = _model_rates(CHAT_RATES_USD_PER_MILLION, model)
    if rates is None:
        raise ValueError(f"Modelo sem tarifa cadastrada: {model}")
    input_rate, cached_rate, output_rate = rates
    uncached = max(input_tokens - cached_input_tokens, 0)
    cost = (
        Decimal(uncached) * input_rate
        + Decimal(cached_input_tokens) * cached_rate
        + Decimal(output_tokens) * output_rate
    ) / Decimal(1_000_000)
    return _charge(cost, markup_multiplier)


def image_token_charge(
    model: str,
    *,
    input_image_tokens: int,
    input_text_tokens: int,
    output_image_tokens: int,
    markup_multiplier: Decimal = DEFAULT_MARKUP_MULTIPLIER,
) -> CreditCharge:
    rates = _model_rates(IMAGE_TOKEN_RATES_USD_PER_MILLION, model)
    if rates is None:
        raise ValueError(f"Modelo de imagem sem tarifa cadastrada: {model}")
    image_input_rate, text_input_rate, output_rate = rates
    cost = (
        Decimal(input_image_tokens) * image_input_rate
        + Decimal(input_text_tokens) * text_input_rate
        + Decimal(output_image_tokens) * output_rate
    ) / Decimal(1_000_000)
    return _charge(cost, markup_multiplier)


def _model_rates(
    catalog: dict[str, tuple[Decimal, Decimal, Decimal]], model: str
) -> tuple[Decimal, Decimal, Decimal] | None:
    if model in catalog:
        return catalog[model]
    matches = [rates for name, rates in catalog.items() if model.startswith(f"{name}-")]
    return matches[0] if len(matches) == 1 else None


def _charge(cost: Decimal, markup_multiplier: Decimal) -> CreditCharge:
    retail = cost * markup_multiplier
    credits = int((retail / CREDIT_VALUE_USD).to_integral_value(rounding=ROUND_CEILING))
    return CreditCharge(cost, retail, max(credits, 1 if cost > 0 else 0))


class CreditLedgerService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def account(self, tenant_id: UUID, *, lock: bool = False) -> CreditAccountModel:
        statement = select(CreditAccountModel).where(CreditAccountModel.tenant_id == tenant_id)
        if lock:
            statement = statement.with_for_update()
        account = self._session.scalar(statement)
        if account is None:
            account = CreditAccountModel(tenant_id=tenant_id)
            self._session.add(account)
            self._session.flush()
        return account

    def ensure_available(self, tenant_id: UUID, *, resource: str) -> None:
        account = self.account(tenant_id)
        if resource == "ai_message" and account.unlimited_messages:
            return
        if account.enforcement_mode == "enforce" and account.balance_credits <= 0:
            raise PaymentRequiredError("Créditos insuficientes para usar este recurso")

    def reserve(
        self,
        tenant_id: UUID,
        *,
        resource: str,
        model: str,
        estimate: CreditCharge,
        idempotency_key: str,
        reference_id: UUID | None,
        ttl_seconds: int = 900,
    ) -> CreditReservationModel:
        existing = self._session.scalar(
            select(CreditReservationModel).where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.idempotency_key == idempotency_key,
            )
        )
        if existing is not None and existing.status in ("reserved", "started", "settled"):
            return existing
        account = self.account(tenant_id, lock=True)
        if existing is None:
            existing = self._session.scalar(
                select(CreditReservationModel).where(
                    CreditReservationModel.tenant_id == tenant_id,
                    CreditReservationModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None and existing.status in (
                "reserved",
                "started",
                "settled",
            ):
                self._session.commit()
                return existing
        held = 0 if resource == "ai_message" and account.unlimited_messages else estimate.credits
        available = account.balance_credits - account.reserved_credits
        if account.enforcement_mode == "enforce" and available < held:
            raise PaymentRequiredError(
                "Créditos disponíveis insuficientes para reservar a operação"
            )
        account.reserved_credits += held
        now = datetime.now(UTC)
        snapshot = {
            "estimated_provider_cost_usd": str(estimate.provider_cost_usd),
            "estimated_retail_cost_usd": str(estimate.retail_cost_usd),
            "pricing_catalog_version": PRICING_CATALOG_VERSION,
            "credit_value_usd": str(CREDIT_VALUE_USD),
            "markup_multiplier": str(DEFAULT_MARKUP_MULTIPLIER),
            "enforcement_mode_snapshot": account.enforcement_mode,
            "unlimited_messages_snapshot": account.unlimited_messages,
        }
        if existing is None:
            existing = CreditReservationModel(
                id=uuid4(),
                tenant_id=tenant_id,
                resource=resource,
                model=model,
                idempotency_key=idempotency_key,
                status="reserved",
                reserved_credits=held,
                reference_id=reference_id,
                extra=snapshot,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            self._session.add(existing)
        else:
            existing.status = "reserved"
            existing.reserved_credits = held
            existing.actual_credits = None
            existing.extra = snapshot
            existing.expires_at = now + timedelta(seconds=ttl_seconds)
            existing.settled_at = None
        self._session.commit()
        return existing

    def settle_reservation(
        self,
        tenant_id: UUID,
        *,
        idempotency_key: str,
        charge: CreditCharge,
        model: str,
        reference_id: UUID | None,
        extra: dict,
    ) -> CreditLedgerModel:
        reservation = self._session.scalar(
            select(CreditReservationModel)
            .where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if reservation is None:
            raise RuntimeError("Credit reservation not found")
        if reservation.status == "released":
            raise CreditReservationClosed("Credit reservation was already released")
        existing = self._session.scalar(
            select(CreditLedgerModel).where(
                CreditLedgerModel.tenant_id == tenant_id,
                CreditLedgerModel.idempotency_key == f"settle:{idempotency_key}",
            )
        )
        if existing is not None:
            return existing
        if reservation.status == "settled":
            raise CreditReservationClosed("Settled reservation is missing its ledger entry")
        account = self.account(tenant_id, lock=True)
        account.reserved_credits = max(
            account.reserved_credits - reservation.reserved_credits, 0
        )
        reservation.status = "settled"
        unlimited_snapshot = bool(
            reservation.extra.get("unlimited_messages_snapshot", False)
        )
        reservation.actual_credits = (
            0
            if reservation.resource == "ai_message" and unlimited_snapshot
            else charge.credits
        )
        reservation.reference_id = reference_id
        reservation.settled_at = datetime.now(UTC)
        reservation.extra = {**reservation.extra, **extra}
        return self.consume(
            tenant_id,
            resource=reservation.resource,
            model=model,
            charge=charge,
            idempotency_key=f"settle:{idempotency_key}",
            reference_id=reference_id,
            extra=extra,
            allow_overage=True,
            credits_override=reservation.actual_credits,
        )

    def start_reservation(self, tenant_id: UUID, idempotency_key: str) -> None:
        reservation = self._session.scalar(
            select(CreditReservationModel)
            .where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if reservation is None:
            raise RuntimeError("Credit reservation not found")
        if reservation.status == "settled":
            return
        reservation.status = "started"
        self._session.commit()

    def touch_reservation(
        self, tenant_id: UUID, idempotency_key: str, ttl_seconds: int = 900
    ) -> bool:
        reservation = self._session.scalar(
            select(CreditReservationModel)
            .where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.idempotency_key == idempotency_key,
                CreditReservationModel.status.in_(("reserved", "started")),
            )
            .with_for_update()
        )
        if reservation is None:
            return False
        reservation.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        self._session.commit()
        return True

    def reservation_status(self, tenant_id: UUID, idempotency_key: str) -> str | None:
        return self._session.scalar(
            select(CreditReservationModel.status).where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.idempotency_key == idempotency_key,
            )
        )

    def record_accepted_ai_call(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        *,
        model: str,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
    ) -> None:
        reservation = self._session.scalar(
            select(CreditReservationModel)
            .where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.idempotency_key == idempotency_key,
                CreditReservationModel.status == "started",
            )
            .with_for_update()
        )
        if reservation is None:
            raise CreditReservationClosed("Active reservation not found")
        extra = dict(reservation.extra)
        extra["accepted_call_count"] = int(extra.get("accepted_call_count", 0)) + 1
        extra["accepted_model"] = model
        extra["accepted_input_tokens"] = int(
            extra.get("accepted_input_tokens", 0)
        ) + input_tokens
        extra["accepted_cached_input_tokens"] = int(
            extra.get("accepted_cached_input_tokens", 0)
        ) + cached_input_tokens
        extra["accepted_output_tokens"] = int(
            extra.get("accepted_output_tokens", 0)
        ) + output_tokens
        reservation.extra = extra
        reservation.expires_at = datetime.now(UTC) + timedelta(seconds=900)
        self._session.commit()

    def reservation_extra(self, tenant_id: UUID, idempotency_key: str) -> dict | None:
        value = self._session.scalar(
            select(CreditReservationModel.extra).where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.idempotency_key == idempotency_key,
            )
        )
        return dict(value) if value is not None else None

    def release_reservation(
        self, tenant_id: UUID, idempotency_key: str, *, commit: bool = True
    ) -> bool:
        reservation = self._session.scalar(
            select(CreditReservationModel)
            .where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if reservation is None or reservation.status not in ("reserved", "started"):
            return False
        account = self.account(tenant_id, lock=True)
        account.reserved_credits = max(
            account.reserved_credits - reservation.reserved_credits, 0
        )
        reservation.status = "released"
        reservation.settled_at = datetime.now(UTC)
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return True

    def reconcile_expired(self) -> int:
        reservations = self._session.scalars(
            select(CreditReservationModel)
            .where(
                CreditReservationModel.status.in_(("reserved", "started")),
                CreditReservationModel.expires_at < datetime.now(UTC),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for reservation in reservations:
            account = self.account(reservation.tenant_id, lock=True)
            account.reserved_credits = max(
                account.reserved_credits - reservation.reserved_credits, 0
            )
            if reservation.status == "started":
                charge = CreditCharge(
                    provider_cost_usd=Decimal(
                        reservation.extra["estimated_provider_cost_usd"]
                    ),
                    retail_cost_usd=Decimal(
                        reservation.extra["estimated_retail_cost_usd"]
                    ),
                    credits=reservation.reserved_credits,
                )
                self.consume(
                    reservation.tenant_id,
                    resource=reservation.resource,
                    model=reservation.model,
                    charge=charge,
                    idempotency_key=f"reconcile:{reservation.idempotency_key}",
                    reference_id=reservation.reference_id,
                    extra={"reconciled_from_expired_started_reservation": True},
                    allow_overage=True,
                    credits_override=reservation.reserved_credits,
                )
                reservation.status = "settled"
                reservation.actual_credits = reservation.reserved_credits
            else:
                reservation.status = "released"
            reservation.settled_at = datetime.now(UTC)
        self._session.commit()
        return len(reservations)

    def grant(
        self,
        tenant_id: UUID,
        credits: int,
        *,
        idempotency_key: str,
        description: str,
        created_by: UUID,
    ) -> CreditLedgerModel:
        if credits <= 0:
            raise ValueError("credits must be positive")
        return self._post(
            tenant_id,
            delta=credits,
            kind="grant",
            resource=None,
            model=None,
            charge=None,
            idempotency_key=idempotency_key,
            description=description,
            reference_id=None,
            created_by=created_by,
            extra={},
        )

    def consume(
        self,
        tenant_id: UUID,
        *,
        resource: str,
        model: str,
        charge: CreditCharge,
        idempotency_key: str,
        reference_id: UUID | None,
        extra: dict,
        allow_overage: bool = False,
        credits_override: int | None = None,
    ) -> CreditLedgerModel:
        account = self.account(tenant_id)
        credits = (
            credits_override
            if credits_override is not None
            else 0
            if resource == "ai_message" and account.unlimited_messages
            else charge.credits
        )
        return self._post(
            tenant_id,
            delta=-credits,
            kind="usage",
            resource=resource,
            model=model,
            charge=charge,
            idempotency_key=idempotency_key,
            description=None,
            reference_id=reference_id,
            created_by=None,
            extra=extra,
            allow_overage=allow_overage,
        )

    def _post(
        self,
        tenant_id: UUID,
        *,
        delta: int,
        kind: str,
        resource: str | None,
        model: str | None,
        charge: CreditCharge | None,
        idempotency_key: str,
        description: str | None,
        reference_id: UUID | None,
        created_by: UUID | None,
        extra: dict,
        allow_overage: bool = False,
    ) -> CreditLedgerModel:
        existing = self._session.scalar(
            select(CreditLedgerModel).where(
                CreditLedgerModel.tenant_id == tenant_id,
                CreditLedgerModel.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        account = self.account(tenant_id, lock=True)
        next_balance = account.balance_credits + delta
        if (
            not allow_overage
            and account.enforcement_mode == "enforce"
            and next_balance - account.reserved_credits < 0
        ):
            raise PaymentRequiredError("Créditos insuficientes para concluir o consumo")
        account.balance_credits = next_balance
        transaction = CreditLedgerModel(
            id=uuid4(),
            tenant_id=tenant_id,
            delta_credits=delta,
            balance_after=next_balance,
            kind=kind,
            resource=resource,
            model=model,
            provider_cost_usd=charge.provider_cost_usd if charge else Decimal("0"),
            retail_cost_usd=charge.retail_cost_usd if charge else Decimal("0"),
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            description=description,
            extra=extra,
            created_by=created_by,
        )
        self._session.add(transaction)
        try:
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            existing = self._session.scalar(
                select(CreditLedgerModel).where(
                    CreditLedgerModel.tenant_id == tenant_id,
                    CreditLedgerModel.idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            return existing
        return transaction
