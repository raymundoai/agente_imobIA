from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.modules.activity.models import ActivityLogModel


def model_snapshot(model: Any, *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """Column values of a row as JSON-friendly data, kept so a deletion can be reviewed."""

    snapshot: dict[str, Any] = {}
    for column in inspect(model).mapper.column_attrs:
        if column.key in exclude:
            continue
        value = getattr(model, column.key)
        if value is None or isinstance(value, (str, int, float, bool)):
            snapshot[column.key] = value
        elif isinstance(value, (list, tuple)):
            snapshot[column.key] = [str(item) for item in value]
        elif isinstance(value, dict):
            snapshot[column.key] = value
        else:
            snapshot[column.key] = str(value)
    return snapshot


def record_activity(
    session: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None,
    entity: str,
    entity_id: UUID | None,
    action: str,
    summary: str,
    snapshot: dict[str, Any] | None = None,
) -> None:
    """Adds the entry to the caller's transaction, so it is saved together with the change."""

    session.add(
        ActivityLogModel(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_type="user" if actor_user_id else "system",
            entity=entity,
            entity_id=entity_id,
            action=action,
            summary=summary,
            snapshot=snapshot or {},
        )
    )
