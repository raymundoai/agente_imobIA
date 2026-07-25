from __future__ import annotations

import os
import socket
import threading
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

from app.container import Container
from app.modules.ai.adapters.repositories import (
    SqlAlchemyAiAuditLogRepository,
    SqlAlchemyKnowledgeRepository,
)
from app.modules.ai.application.use_cases import GenerateAiReplyUseCase
from app.modules.ai.domain.ports import (
    AiProviderDispatchUncertainError,
    AiProviderRejectedError,
)
from app.modules.billing_usage.service import (
    CreditLedgerService,
    chat_charge,
    estimated_chat_charge,
)
from app.modules.contacts.service import ContactUpsertService
from app.modules.conversations.adapters.repositories import SqlAlchemyConversationRepository
from app.modules.conversations.application.use_cases import lead_agent_is_active
from app.modules.conversations.domain.entities import ConversationMode
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.application.use_cases import LeadQualificationService
from app.modules.messaging.models import MessageJobModel
from app.modules.messaging.service import MessageJobRepository
from app.modules.properties.adapters.repositories import SqlAlchemyPropertyRepository
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository


class AmbiguousAiCall(RuntimeError):
    pass


class SafeAiFailure(RuntimeError):
    pass


class MessageJobProcessor:
    def __init__(self, container: Container, worker_id: str | None = None) -> None:
        self.container = container
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid4()}"

    def process_next(self, tenant_id: UUID | None = None) -> dict[str, Any] | None:
        with self.container.database.session_factory() as session:
            CreditLedgerService(session).reconcile_expired()
            job = MessageJobRepository(session).claim_next(
                self.container.settings.message_job_stale_seconds,
                self.worker_id,
                tenant_id,
            )
            if job is None:
                return None
            snapshot = self._snapshot(job)
        if snapshot["stage"] == "delivery":
            return self._deliver(snapshot)
        return self._generate(snapshot)

    def _generate(self, job: dict[str, Any]) -> dict[str, Any]:
        try:
            with self.container.database.session_factory() as session:
                repository = MessageJobRepository(session)
                persisted = session.get(MessageJobModel, job["id"])
                if persisted is None:
                    raise RuntimeError("Message job not found")
                recovered = repository.recover_generated(persisted)
            if recovered is not None:
                result = {"response_text": recovered, "recovered": True}
            else:
                self._assert_lease(job)
                with self._heartbeat(job):
                    result = self._generate_once(job)
            with self.container.database.session_factory() as session:
                status = MessageJobRepository(session).generation_completed(
                    job["id"],
                    job["lease_token"],
                    str(result.get("response_text") or ""),
                    result,
                    should_deliver=job["send_to_channel"]
                    and not bool(result.get("skipped")),
                )
            return {"id": str(job["id"]), "status": status, **result}
        except Exception as exc:
            with self.container.database.session_factory() as session:
                if not isinstance(exc, AmbiguousAiCall):
                    CreditLedgerService(session).release_reservation(
                        job["tenant_id"], self._reservation_key(job["id"])
                    )
                status = MessageJobRepository(session).fail_generation(
                    job["id"],
                    job["lease_token"],
                    str(exc),
                    self.container.settings.message_job_backoff_seconds,
                    permanent=isinstance(exc, AmbiguousAiCall),
                )
            return {"id": str(job["id"]), "status": status, "error": str(exc)}

    def _generate_once(self, job: dict[str, Any]) -> dict[str, Any]:
        if self.container.ai_provider is None:
            raise RuntimeError("OpenAI integration is not configured")
        with self.container.database.session_factory() as session:
            tenants = SqlAlchemyTenantRepository(session)
            tenant = tenants.get_by_id(job["tenant_id"])
            if tenant is None:
                raise RuntimeError("Tenant not found")
            if not lead_agent_is_active(tenant.settings):
                return {"response_text": "", "skipped": "agent_inactive"}
            conversations = SqlAlchemyConversationRepository(session)
            conversation = conversations.get_by_id(job["tenant_id"], job["conversation_id"])
            if conversation is None:
                raise RuntimeError("Conversation not found")
            if conversation.mode is not ConversationMode.AI:
                return {"response_text": "", "skipped": "human_handoff"}
            ledger = CreditLedgerService(session)
            reservation = ledger.reserve(
                job["tenant_id"],
                resource="ai_message",
                model=self.container.settings.openai_chat_model,
                estimate=estimated_chat_charge(
                    self.container.settings.openai_chat_model
                ),
                idempotency_key=self._reservation_key(job["id"]),
                reference_id=job["id"],
            )
            if reservation.status == "started":
                raise AmbiguousAiCall(
                    "Chamada de IA anterior sem resultado persistido; reconciliação necessária"
                )
            if reservation.status == "settled":
                raise AmbiguousAiCall(
                    "Reserva já reconciliada sem resposta persistida; revisão manual necessária"
                )
            credentials, channel = self._channel(job["channel"])
            try:
                result = GenerateAiReplyUseCase(
                    tenants,
                    conversations,
                    self.container.ai_provider,
                    SqlAlchemyKnowledgeRepository(session),
                    SqlAlchemyAiAuditLogRepository(
                        session,
                        credit_reservation_key=self._reservation_key(job["id"]),
                    ),
                    credentials,
                    channel,
                    self.container.event_bus,
                    LeadQualificationService(
                        tenants,
                        SqlAlchemyLeadDemandRepository(session),
                        self.container.crm_credentials,
                        self.container.crm,
                        self.container.event_bus,
                        ContactUpsertService(session),
                    ),
                    properties=SqlAlchemyPropertyRepository(session),
                ).execute(
                    job["tenant_id"],
                    job["conversation_id"],
                    send_to_channel=False,
                    outbound_message_id=job["id"],
                    side_effect_guard=lambda: self._assert_lease(job),
                    dispatch_guard=lambda: self._mark_dispatched(job),
                    usage_observer=lambda response: self._record_accepted_call(
                        job, response
                    ),
                )
            except AiProviderRejectedError as exc:
                if self._accepted_call_count(job) > 0:
                    self._settle_partial_usage(job)
                    raise AmbiguousAiCall(
                        "Nova chamada rejeitada após uso anterior confirmado"
                    ) from exc
                raise SafeAiFailure("OpenAI rejeitou a requisição antes da aceitação") from exc
            except AiProviderDispatchUncertainError as exc:
                if self._accepted_call_count(job) > 0:
                    self._settle_partial_usage(job)
                raise AmbiguousAiCall(
                    "Dispatch OpenAI ambíguo; reconciliação necessária"
                ) from exc
            except Exception as exc:
                if self._reservation_started(job):
                    if self._accepted_call_count(job) > 0:
                        self._settle_partial_usage(job)
                    raise AmbiguousAiCall(
                        "Falha após dispatch da IA; reconciliação necessária"
                    ) from exc
                raise SafeAiFailure("Falha definitiva antes do dispatch da IA") from exc
            return {
                "response_text": result.response_text,
                "model": result.model,
                "tokens_used": result.tokens_used,
            }

    def _deliver(self, job: dict[str, Any]) -> dict[str, Any]:
        try:
            with self.container.database.session_factory() as session:
                tenants = SqlAlchemyTenantRepository(session)
                tenant = tenants.get_by_id(job["tenant_id"])
                conversations = SqlAlchemyConversationRepository(session)
                conversation = conversations.get_by_id(
                    job["tenant_id"], job["conversation_id"]
                )
                if tenant is None or conversation is None:
                    raise RuntimeError("Tenant or conversation not found")
                credentials_provider, channel = self._channel(job["channel"])
                credentials = credentials_provider.get(tenant.slug)
                if credentials is None:
                    raise RuntimeError("Canal de mensagens não configurado")
                self._assert_lease(job)
                with self._heartbeat(job):
                    sent = channel.send_message(
                        credentials,
                        conversation.phone,
                        job["response_text"],
                        idempotency_key=(
                            str(job["id"]) if job["channel"] == "whatsapp" else None
                        ),
                    )
            with self.container.database.session_factory() as session:
                MessageJobRepository(session).delivery_completed(
                    job["id"], job["lease_token"], sent.external_message_id
                )
            return {
                "id": str(job["id"]),
                "status": "sent",
                "external_message_id": sent.external_message_id,
            }
        except Exception as exc:
            # The remote call may have succeeded before the connection failed. Never
            # automatically resend an ambiguous delivery.
            with self.container.database.session_factory() as session:
                MessageJobRepository(session).delivery_unknown(
                    job["id"], job["lease_token"], str(exc)
                )
            return {
                "id": str(job["id"]),
                "status": "delivery_unknown",
                "error": str(exc),
            }

    def _channel(
        self, channel_name: str
    ) -> tuple[ChannelCredentialsPort, MessageChannelPort]:
        if channel_name == "telegram":
            return self.container.telegram_credentials, self.container.telegram_channel
        return self.container.channel_credentials, self.container.message_channel

    @staticmethod
    def _snapshot(job: MessageJobModel) -> dict[str, Any]:
        return {
            "id": job.id,
            "tenant_id": job.tenant_id,
            "conversation_id": job.conversation_id,
            "channel": job.channel,
            "stage": job.stage,
            "send_to_channel": job.send_to_channel,
            "response_text": job.response_text or "",
            "lease_token": job.lease_token,
        }

    @contextmanager
    def _heartbeat(self, job: dict[str, Any]):
        stopped = threading.Event()
        interval = max(self.container.settings.message_job_stale_seconds / 3, 1)

        def maintain() -> None:
            while not stopped.wait(interval):
                with self.container.database.session_factory() as session:
                    MessageJobRepository(session).heartbeat(
                        job["id"],
                        job["lease_token"],
                        self.container.settings.message_job_stale_seconds,
                    )
                    CreditLedgerService(session).touch_reservation(
                        job["tenant_id"], self._reservation_key(job["id"])
                    )

        thread = threading.Thread(target=maintain, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(timeout=2)

    def _assert_lease(self, job: dict[str, Any]) -> None:
        with self.container.database.session_factory() as session:
            MessageJobRepository(session).heartbeat(
                job["id"],
                job["lease_token"],
                self.container.settings.message_job_stale_seconds,
            )
            CreditLedgerService(session).touch_reservation(
                job["tenant_id"], self._reservation_key(job["id"])
            )

    @staticmethod
    def _reservation_key(job_id: UUID) -> str:
        return f"ai-message:{job_id}"

    def _mark_dispatched(self, job: dict[str, Any]) -> None:
        self._assert_lease(job)
        with self.container.database.session_factory() as session:
            CreditLedgerService(session).start_reservation(
                job["tenant_id"], self._reservation_key(job["id"])
            )

    def _reservation_started(self, job: dict[str, Any]) -> bool:
        with self.container.database.session_factory() as session:
            return (
                CreditLedgerService(session).reservation_status(
                    job["tenant_id"], self._reservation_key(job["id"])
                )
                == "started"
            )

    def _record_accepted_call(self, job: dict[str, Any], response: Any) -> None:
        with self.container.database.session_factory() as session:
            CreditLedgerService(session).record_accepted_ai_call(
                job["tenant_id"],
                self._reservation_key(job["id"]),
                model=response.model,
                input_tokens=response.input_tokens,
                cached_input_tokens=response.cached_input_tokens,
                output_tokens=response.output_tokens,
            )

    def _accepted_call_count(self, job: dict[str, Any]) -> int:
        with self.container.database.session_factory() as session:
            extra = CreditLedgerService(session).reservation_extra(
                job["tenant_id"], self._reservation_key(job["id"])
            )
        return int((extra or {}).get("accepted_call_count", 0))

    def _settle_partial_usage(self, job: dict[str, Any]) -> None:
        with self.container.database.session_factory() as session:
            ledger = CreditLedgerService(session)
            extra = ledger.reservation_extra(
                job["tenant_id"], self._reservation_key(job["id"])
            )
            if not extra:
                return
            try:
                charge = chat_charge(
                    str(extra["accepted_model"]),
                    input_tokens=int(extra.get("accepted_input_tokens", 0)),
                    cached_input_tokens=int(
                        extra.get("accepted_cached_input_tokens", 0)
                    ),
                    output_tokens=int(extra.get("accepted_output_tokens", 0)),
                )
            except (KeyError, ValueError):
                return
            ledger.settle_reservation(
                job["tenant_id"],
                idempotency_key=self._reservation_key(job["id"]),
                charge=charge,
                model=str(extra["accepted_model"]),
                reference_id=job["id"],
                extra={
                    "partial_usage": True,
                    "accepted_call_count": int(extra["accepted_call_count"]),
                    "input_tokens": int(extra.get("accepted_input_tokens", 0)),
                    "cached_input_tokens": int(
                        extra.get("accepted_cached_input_tokens", 0)
                    ),
                    "output_tokens": int(extra.get("accepted_output_tokens", 0)),
                },
            )
            session.commit()
