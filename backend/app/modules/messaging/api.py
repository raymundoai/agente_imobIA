from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, require_roles
from app.modules.messaging.models import MessageJobModel
from app.modules.messaging.service import MessageJobRepository
from app.modules.users.domain.entities import UserRole
from app.shared.errors.exceptions import NotFoundError

router = APIRouter(prefix="/message-jobs", tags=["message-jobs"])


class MessageJobResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    message_id: UUID
    channel: str
    status: str
    stage: str
    attempts: int
    max_attempts: int
    available_at: datetime
    last_error: str | None
    result: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_model(cls, job: MessageJobModel) -> "MessageJobResponse":
        return cls.model_validate(job, from_attributes=True)


@router.get("", response_model=list[MessageJobResponse])
def list_jobs(
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR)
    ),
    session: Session = Depends(get_db_session),
) -> list[MessageJobResponse]:
    return [
        MessageJobResponse.from_model(job)
        for job in MessageJobRepository(session).list(principal.tenant_id, status, limit)
    ]


@router.post("/{job_id}/retry", response_model=MessageJobResponse)
def retry_job(
    job_id: UUID,
    principal: CurrentPrincipal = Depends(
        require_roles(UserRole.ADMIN, UserRole.GESTOR)
    ),
    session: Session = Depends(get_db_session),
) -> MessageJobResponse:
    job = MessageJobRepository(session).retry(principal.tenant_id, job_id)
    if job is None:
        raise NotFoundError("Failed or retrying message job not found")
    return MessageJobResponse.from_model(job)
