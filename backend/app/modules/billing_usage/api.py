from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.billing_usage.adapters.models import UsageRecordModel

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageSummaryItem(BaseModel):
    type: str
    module: str
    quantity: int
    estimated_cost: Decimal


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
