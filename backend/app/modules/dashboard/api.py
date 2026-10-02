from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.contacts.models import ContactModel
from app.modules.conversations.adapters.models import ConversationModel
from app.modules.leads.adapters.models import LeadDemandModel
from app.modules.properties.adapters.models import PropertyModel
from app.modules.tenants.adapters.models import TenantModel
from app.shared.errors.exceptions import ApplicationError

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

CONTACT_KINDS = ("lead", "owner", "tenant", "client")
TIMELINE_PERIODS = (7, 30, 90)
DEFAULT_TIMEZONE = "America/Sao_Paulo"


class DashboardStats(BaseModel):
    contacts: int
    contacts_by_kind: dict[str, int]
    search_demands: int
    properties: int
    conversations: int


class ConversationTimelinePoint(BaseModel):
    date: date
    conversations: int


class ConversationTimeline(BaseModel):
    days: int
    timezone: str
    total: int
    points: list[ConversationTimelinePoint]


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> DashboardStats:
    tenant_id = principal.tenant_id
    by_kind = dict.fromkeys(CONTACT_KINDS, 0)
    for kind, count in session.execute(
        select(ContactModel.kind, func.count())
        .where(ContactModel.tenant_id == tenant_id)
        .group_by(ContactModel.kind)
    ):
        by_kind[kind] = int(count)
    search_demands = session.scalar(
        select(func.count())
        .select_from(LeadDemandModel)
        .where(LeadDemandModel.tenant_id == tenant_id)
    )
    properties = session.scalar(
        select(func.count())
        .select_from(PropertyModel)
        .where(PropertyModel.tenant_id == tenant_id, PropertyModel.source == "manual")
    )
    conversations = session.scalar(
        select(func.count())
        .select_from(ConversationModel)
        .where(ConversationModel.tenant_id == tenant_id, ConversationModel.is_group.is_(False))
    )
    return DashboardStats(
        contacts=sum(by_kind.values()),
        contacts_by_kind=by_kind,
        search_demands=int(search_demands or 0),
        properties=int(properties or 0),
        conversations=int(conversations or 0),
    )


@router.get("/conversations-timeline", response_model=ConversationTimeline)
def conversations_timeline(
    days: Annotated[int, Query()] = 30,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ConversationTimeline:
    """Conversations started per day, by AI or human, in the tenant's timezone."""

    if days not in TIMELINE_PERIODS:
        raise InvalidPeriodError("Período deve ser de 7, 30 ou 90 dias")

    timezone = _tenant_timezone(session, principal.tenant_id)
    zone = ZoneInfo(timezone)
    today = datetime.now(UTC).astimezone(zone).date()
    first_day = today - timedelta(days=days - 1)
    starts_at = datetime.combine(first_day, datetime.min.time(), tzinfo=zone)
    local_day = func.date(func.timezone(timezone, ConversationModel.started_at))
    counts = {
        day: int(count)
        for day, count in session.execute(
            select(local_day, func.count())
            .where(
                ConversationModel.tenant_id == principal.tenant_id,
                ConversationModel.is_group.is_(False),
                ConversationModel.started_at >= starts_at,
            )
            .group_by(local_day)
        )
    }
    points = [
        ConversationTimelinePoint(date=day, conversations=counts.get(day, 0))
        for day in (first_day + timedelta(days=offset) for offset in range(days))
    ]
    return ConversationTimeline(
        days=days,
        timezone=timezone,
        total=sum(point.conversations for point in points),
        points=points,
    )


class InvalidPeriodError(ApplicationError):
    status_code = 422
    code = "invalid_period"


def _tenant_timezone(session: Session, tenant_id: object) -> str:
    tenant = session.get(TenantModel, tenant_id)
    settings = tenant.settings if tenant is not None and isinstance(tenant.settings, dict) else {}
    profile = settings.get("profile") if isinstance(settings.get("profile"), dict) else {}
    hours = profile.get("business_hours") if isinstance(profile.get("business_hours"), dict) else {}
    timezone = hours.get("timezone")
    if not isinstance(timezone, str):
        return DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_TIMEZONE
    return timezone
