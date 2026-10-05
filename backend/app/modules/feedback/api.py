from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.feedback.models import FeedbackReportModel
from app.modules.platform.api import PlatformPrincipal, get_platform_principal
from app.modules.tenants.adapters.models import TenantModel
from app.modules.users.adapters.models import UserModel
from app.shared.errors.exceptions import ConflictError, NotFoundError

router = APIRouter(prefix="/feedback", tags=["feedback"])
platform_router = APIRouter(prefix="/platform/feedback", tags=["platform"])

# A burst of reports from one person is almost always a stuck submit button.
MAX_REPORTS_PER_HOUR = 10


class FeedbackRequest(BaseModel):
    kind: str = Field(pattern="^(problem|suggestion|question|praise)$")
    message: str = Field(min_length=5, max_length=5000)
    page: str | None = Field(default=None, max_length=300)
    contact_phone: str | None = Field(default=None, max_length=30)


class FeedbackCreated(BaseModel):
    id: UUID


@router.post("", response_model=FeedbackCreated, status_code=201)
def send_feedback(
    payload: FeedbackRequest,
    user_agent: Annotated[str | None, Header()] = None,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> FeedbackCreated:
    """Name, e-mail and company come from the account; the person only describes the case."""

    recent = session.scalar(
        select(func.count()).where(
            FeedbackReportModel.user_id == principal.user_id,
            FeedbackReportModel.created_at > func.now() - func.make_interval(0, 0, 0, 0, 1),
        )
    )
    if (recent or 0) >= MAX_REPORTS_PER_HOUR:
        raise ConflictError(
            "Você já enviou vários relatos agora há pouco. Tente de novo mais tarde."
        )
    report = FeedbackReportModel(
        id=uuid4(),
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        kind=payload.kind,
        message=payload.message.strip(),
        page=(payload.page or "").strip() or None,
        contact_phone=(payload.contact_phone or "").strip() or None,
        user_agent=(user_agent or "")[:300] or None,
    )
    session.add(report)
    session.commit()
    return FeedbackCreated(id=report.id)


class FeedbackItem(BaseModel):
    id: UUID
    kind: str
    message: str
    page: str | None
    status: str
    admin_note: str | None
    created_at: datetime
    resolved_at: datetime | None
    tenant_name: str
    user_name: str | None
    user_email: str | None
    contact_phone: str | None
    user_agent: str | None


class FeedbackUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(new|in_progress|resolved)$")
    admin_note: str | None = Field(default=None, max_length=2000)


def _item(report: FeedbackReportModel, tenant: TenantModel, user: UserModel | None) -> FeedbackItem:
    profile = (tenant.settings or {}).get("profile") if isinstance(tenant.settings, dict) else None
    tenant_name = (profile or {}).get("display_name") or tenant.name
    return FeedbackItem(
        id=report.id,
        kind=report.kind,
        message=report.message,
        page=report.page,
        status=report.status,
        admin_note=report.admin_note,
        created_at=report.created_at,
        resolved_at=report.resolved_at,
        tenant_name=tenant_name,
        user_name=user.name if user else None,
        user_email=user.email if user else None,
        contact_phone=report.contact_phone,
        user_agent=report.user_agent,
    )


@platform_router.get("", response_model=list[FeedbackItem])
def list_feedback(
    status: Annotated[str | None, Query(pattern="^(new|in_progress|resolved)$")] = None,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> list[FeedbackItem]:
    query = (
        select(FeedbackReportModel, TenantModel, UserModel)
        .join(TenantModel, TenantModel.id == FeedbackReportModel.tenant_id)
        .outerjoin(UserModel, UserModel.id == FeedbackReportModel.user_id)
        .order_by(FeedbackReportModel.created_at.desc())
        .limit(200)
    )
    if status:
        query = query.where(FeedbackReportModel.status == status)
    return [_item(report, tenant, user) for report, tenant, user in session.execute(query).all()]


@platform_router.patch("/{report_id}", response_model=FeedbackItem)
def update_feedback(
    report_id: UUID,
    payload: FeedbackUpdate,
    _: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_db_session),
) -> FeedbackItem:
    report = session.get(FeedbackReportModel, report_id)
    if report is None:
        raise NotFoundError("Relato não encontrado")
    if payload.status is not None:
        report.status = payload.status
        report.resolved_at = datetime.now(UTC) if payload.status == "resolved" else None
    if payload.admin_note is not None:
        report.admin_note = payload.admin_note.strip() or None
    session.commit()
    tenant = session.get(TenantModel, report.tenant_id)
    user = session.get(UserModel, report.user_id) if report.user_id else None
    if tenant is None:
        raise NotFoundError("Cliente não encontrado")
    return _item(report, tenant, user)
