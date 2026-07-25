from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.billing_usage.adapters.models import CreditLedgerModel, UsageRecordModel
from app.modules.billing_usage.service import (
    CHAT_RATES_USD_PER_MILLION,
    CREDIT_VALUE_USD,
    DEFAULT_MARKUP_MULTIPLIER,
    IMAGE_TOKEN_RATES_USD_PER_MILLION,
    PRICING_CATALOG_VERSION,
    CreditLedgerService,
)

router = APIRouter(prefix="/usage", tags=["usage"])


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
