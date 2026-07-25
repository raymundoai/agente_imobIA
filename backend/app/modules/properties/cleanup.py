from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.container import Container
from app.modules.properties.adapters.models import PropertyMediaCleanupModel


class PropertyMediaCleanupProcessor:
    """Durable, retryable cleanup consumer shared by the persistent worker."""

    def __init__(self, container: Container) -> None:
        self.container = container

    def process_next(self) -> dict[str, Any] | None:
        with self.container.database.session_factory() as session:
            now = datetime.now(UTC)
            job = session.scalar(
                select(PropertyMediaCleanupModel)
                .where(
                    PropertyMediaCleanupModel.status.in_(("pending", "failed")),
                    PropertyMediaCleanupModel.available_at <= now,
                    PropertyMediaCleanupModel.attempts < 10,
                )
                .order_by(PropertyMediaCleanupModel.available_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.attempts += 1
            try:
                self.container.property_image_storage.delete(job.tenant_id, job.storage_key)
                job.status = "done"
                job.error = None
                job.completed_at = now
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)[:1000]
                delay = min(3600, 5 * (2 ** (job.attempts - 1)))
                job.available_at = now + timedelta(seconds=delay)
            session.commit()
            return {"id": str(job.id), "status": job.status, "attempts": job.attempts}
