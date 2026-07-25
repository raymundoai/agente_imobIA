from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.billing_usage.adapters.models import CreditAccountModel, CreditLedgerModel
from app.shared.errors.exceptions import PaymentRequiredError

CREDIT_VALUE_USD = Decimal("0.001")
DEFAULT_MARKUP_MULTIPLIER = Decimal("2.0")

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
    ) -> CreditLedgerModel:
        account = self.account(tenant_id)
        credits = 0 if resource == "ai_message" and account.unlimited_messages else charge.credits
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
        if account.enforcement_mode == "enforce" and next_balance < 0:
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
