from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.conversations.adapters.models import MessageModel
from app.modules.messaging.models import MessageJobModel


class LostMessageJobLease(RuntimeError):
    pass


class MessageJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def claim_next(
        self,
        lease_seconds: int,
        worker_id: str,
        tenant_id: UUID | None = None,
    ) -> MessageJobModel | None:
        now = datetime.now(UTC)
        # Generation can safely resume: its outbound id is deterministic. Delivery cannot
        # safely resume because Telegram does not offer an idempotency key.
        self.session.execute(
            update(MessageJobModel)
            .where(
                MessageJobModel.status == "processing",
                MessageJobModel.lease_expires_at < now,
                MessageJobModel.stage == "generation",
                MessageJobModel.attempts >= MessageJobModel.max_attempts,
            )
            .values(
                status="failed",
                last_error="Limite de tentativas atingido após perda de lease",
                locked_at=None,
                lease_expires_at=None,
                lease_owner=None,
                lease_token=None,
            )
        )
        self.session.execute(
            update(MessageJobModel)
            .where(
                MessageJobModel.status == "processing",
                MessageJobModel.lease_expires_at < now,
                MessageJobModel.stage == "generation",
                MessageJobModel.attempts < MessageJobModel.max_attempts,
            )
            .values(
                status="retrying",
                available_at=now,
                locked_at=None,
                lease_expires_at=None,
                lease_owner=None,
                lease_token=None,
            )
        )
        self.session.execute(
            update(MessageJobModel)
            .where(
                MessageJobModel.status == "processing",
                MessageJobModel.lease_expires_at < now,
                MessageJobModel.stage == "delivery",
            )
            .values(
                status="delivery_unknown",
                last_error="Worker perdeu o lease durante o envio; reconciliação manual necessária",
                locked_at=None,
                lease_expires_at=None,
                lease_owner=None,
                lease_token=None,
            )
        )
        eligible = ("received", "retrying", "delivery_pending")
        query = select(MessageJobModel).where(
            MessageJobModel.status.in_(eligible),
            MessageJobModel.available_at <= now,
        )
        if tenant_id is not None:
            query = query.where(MessageJobModel.tenant_id == tenant_id)
        job = self.session.scalar(
            query.order_by(MessageJobModel.available_at, MessageJobModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            self.session.commit()
            return None
        job.status = "processing"
        job.attempts += 1
        job.locked_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.lease_owner = worker_id
        job.lease_token = uuid4()
        job.updated_at = now
        self.session.commit()
        return job

    def heartbeat(self, job_id: UUID, token: UUID, lease_seconds: int) -> None:
        changed = self.session.execute(
            update(MessageJobModel)
            .where(
                MessageJobModel.id == job_id,
                MessageJobModel.status == "processing",
                MessageJobModel.lease_token == token,
            )
            .values(lease_expires_at=datetime.now(UTC) + timedelta(seconds=lease_seconds))
        ).rowcount
        self.session.commit()
        if changed != 1:
            raise LostMessageJobLease(str(job_id))

    def generation_completed(
        self,
        job_id: UUID,
        token: UUID,
        response_text: str,
        result: dict[str, Any],
        *,
        should_deliver: bool,
    ) -> str:
        status = "delivery_pending" if should_deliver else "sent"
        stage = "delivery" if should_deliver else "generation"
        changed = self.session.execute(
            update(MessageJobModel)
            .where(
                MessageJobModel.id == job_id,
                MessageJobModel.status == "processing",
                MessageJobModel.lease_token == token,
            )
            .values(
                status=status,
                stage=stage,
                response_text=response_text,
                outbound_message_id=job_id,
                result=result,
                last_error=None,
                locked_at=None,
                lease_expires_at=None,
                lease_owner=None,
                lease_token=None,
                available_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ).rowcount
        self.session.commit()
        if changed != 1:
            raise LostMessageJobLease(str(job_id))
        return status

    def recover_generated(self, job: MessageJobModel) -> str | None:
        outbound = self.session.scalar(
            select(MessageModel).where(
                MessageModel.tenant_id == job.tenant_id,
                MessageModel.id == job.id,
            )
        )
        return outbound.text if outbound is not None else None

    def delivery_completed(
        self, job_id: UUID, token: UUID, external_message_id: str
    ) -> None:
        job = self.session.scalar(
            select(MessageJobModel).where(
                MessageJobModel.id == job_id,
                MessageJobModel.status == "processing",
                MessageJobModel.lease_token == token,
            )
        )
        if job is None:
            raise LostMessageJobLease(str(job_id))
        outbound = self.session.scalar(
            select(MessageModel).where(
                MessageModel.tenant_id == job.tenant_id,
                MessageModel.id == job.outbound_message_id,
            )
        )
        if outbound is None:
            raise RuntimeError("Prepared outbound message is missing")
        outbound.external_message_id = external_message_id
        job.status = "sent"
        job.result = {**job.result, "external_message_id": external_message_id}
        job.last_error = None
        job.locked_at = None
        job.lease_expires_at = None
        job.lease_owner = None
        job.lease_token = None
        job.updated_at = datetime.now(UTC)
        self.session.commit()

    def mark_delivery_part(
        self,
        job_id: UUID,
        token: UUID,
        message_id: UUID,
        part_index: int,
        external_message_id: str,
    ) -> None:
        job = self._leased(job_id, token)
        outbound = self.session.scalar(
            select(MessageModel).where(
                MessageModel.tenant_id == job.tenant_id,
                MessageModel.id == message_id,
            )
        )
        if outbound is None:
            raise RuntimeError("Prepared outbound message part is missing")
        outbound.external_message_id = external_message_id
        delivered = dict(job.result.get("delivered_parts") or {})
        delivered[str(part_index)] = external_message_id
        job.result = {**job.result, "delivered_parts": delivered}
        job.updated_at = datetime.now(UTC)
        self.session.commit()

    def finish_delivery(self, job_id: UUID, token: UUID) -> None:
        job = self._leased(job_id, token)
        job.status = "sent"
        job.last_error = None
        self._release(job, datetime.now(UTC))
        self.session.commit()

    def fail_generation(
        self,
        job_id: UUID,
        token: UUID,
        error: str,
        backoff_seconds: int,
        *,
        permanent: bool = False,
    ) -> str:
        job = self._leased(job_id, token)
        now = datetime.now(UTC)
        exhausted = permanent or job.attempts >= job.max_attempts
        job.status = "failed" if exhausted else "retrying"
        job.available_at = now + timedelta(
            seconds=backoff_seconds * (2 ** max(job.attempts - 1, 0))
        )
        job.last_error = error[:4000]
        self._release(job, now)
        self.session.commit()
        return job.status

    def delivery_unknown(self, job_id: UUID, token: UUID, error: str) -> None:
        job = self._leased(job_id, token)
        job.status = "delivery_unknown"
        job.last_error = error[:4000]
        self._release(job, datetime.now(UTC))
        self.session.commit()

    def retry(self, tenant_id: UUID, job_id: UUID) -> MessageJobModel | None:
        job = self.session.scalar(
            select(MessageJobModel).where(
                MessageJobModel.id == job_id,
                MessageJobModel.tenant_id == tenant_id,
                MessageJobModel.status.in_(("failed", "retrying", "delivery_unknown")),
            )
        )
        if job is None:
            return None
        job.status = "delivery_pending" if job.stage == "delivery" else "retrying"
        job.attempts = 0
        job.available_at = datetime.now(UTC)
        job.last_error = None
        self._release(job, datetime.now(UTC))
        self.session.commit()
        return job

    def list(
        self, tenant_id: UUID, status: str | None, limit: int
    ) -> list[MessageJobModel]:
        query = select(MessageJobModel).where(MessageJobModel.tenant_id == tenant_id)
        if status:
            query = query.where(MessageJobModel.status == status)
        return list(
            self.session.scalars(
                query.order_by(MessageJobModel.created_at.desc()).limit(limit)
            ).all()
        )

    def _leased(self, job_id: UUID, token: UUID) -> MessageJobModel:
        job = self.session.scalar(
            select(MessageJobModel).where(
                MessageJobModel.id == job_id,
                MessageJobModel.status == "processing",
                MessageJobModel.lease_token == token,
            )
        )
        if job is None:
            raise LostMessageJobLease(str(job_id))
        return job

    @staticmethod
    def _release(job: MessageJobModel, now: datetime) -> None:
        job.locked_at = None
        job.lease_expires_at = None
        job.lease_owner = None
        job.lease_token = None
        job.updated_at = now
