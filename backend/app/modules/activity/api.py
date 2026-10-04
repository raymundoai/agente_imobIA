from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.activity.models import ActivityLogModel
from app.modules.auth.api.dependencies import CurrentPrincipal, require_roles
from app.modules.users.adapters.models import UserModel
from app.modules.users.domain.entities import UserRole

router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityItem(BaseModel):
    id: UUID
    actor_type: str
    actor_name: str | None
    entity: str
    entity_id: UUID | None
    action: str
    summary: str
    snapshot: dict[str, Any]
    created_at: datetime


@router.get("", response_model=list[ActivityItem])
def list_activity(
    entity: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN, UserRole.GESTOR)),
    session: Session = Depends(get_db_session),
) -> list[ActivityItem]:
    query = select(ActivityLogModel).where(ActivityLogModel.tenant_id == principal.tenant_id)
    if entity:
        query = query.where(ActivityLogModel.entity == entity)
    rows = session.scalars(query.order_by(ActivityLogModel.created_at.desc()).limit(limit)).all()
    actor_ids = {row.actor_user_id for row in rows if row.actor_user_id}
    names = (
        dict(
            session.execute(
                select(UserModel.id, UserModel.name).where(
                    UserModel.tenant_id == principal.tenant_id, UserModel.id.in_(actor_ids)
                )
            ).all()
        )
        if actor_ids
        else {}
    )
    return [
        ActivityItem(
            id=row.id,
            actor_type=row.actor_type,
            actor_name=names.get(row.actor_user_id) if row.actor_user_id else None,
            entity=row.entity,
            entity_id=row.entity_id,
            action=row.action,
            summary=row.summary,
            snapshot=row.snapshot,
            created_at=row.created_at,
        )
        for row in rows
    ]
