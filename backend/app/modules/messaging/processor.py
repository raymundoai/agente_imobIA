from __future__ import annotations

import os
import socket
import threading
import time
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select

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
from app.modules.billing_usage.commercial import (
    AiAttendanceService,
    CommercialAllowanceExhausted,
    CommercialEntitlementService,
)
from app.modules.billing_usage.service import (
    CreditLedgerService,
    chat_charge,
    estimated_chat_charge,
)
from app.modules.contacts.service import ContactUpsertService
from app.modules.conversations.adapters.models import MessageModel
from app.modules.conversations.adapters.repositories import SqlAlchemyConversationRepository
from app.modules.conversations.application.use_cases import lead_agent_is_active
from app.modules.conversations.domain.entities import (
    ConversationMode,
    Message,
    MessageAuthor,
    MessageDirection,
)
from app.modules.conversations.media import media_path
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.application.use_cases import LeadQualificationService
from app.modules.messaging.models import MessageJobModel
from app.modules.messaging.service import MessageJobRepository
from app.modules.properties.adapters.repositories import SqlAlchemyPropertyRepository
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.shared.events.models import DomainEvent


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
            CommercialEntitlementService(session).reconcile_expired()
            AiAttendanceService(session).close_expired()
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
                with self.container.database.session_factory() as session:
                    attendance_id = AiAttendanceService(session).find_for_job(
                        job["tenant_id"], job["id"]
                    )
                result = {
                    "response_text": recovered,
                    "recovered": True,
                    "commercial_attendance_id": (str(attendance_id) if attendance_id else None),
                }
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
                    should_deliver=job["send_to_channel"] and not bool(result.get("skipped")),
                )
                if not job["send_to_channel"]:
                    AiAttendanceService(session).release_for_job(job["tenant_id"], job["id"])
            return {"id": str(job["id"]), "status": status, **result}
        except Exception as exc:
            with self.container.database.session_factory() as session:
                if not isinstance(exc, AmbiguousAiCall):
                    CreditLedgerService(session).release_reservation(
                        job["tenant_id"], self._reservation_key(job["id"])
                    )
                    AiAttendanceService(session).release_for_job(job["tenant_id"], job["id"])
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
            if not lead_agent_is_active(tenant.settings, str(job["channel"])):
                return {"response_text": "", "skipped": "agent_inactive"}
            conversations = SqlAlchemyConversationRepository(session)
            conversation = conversations.get_by_id(job["tenant_id"], job["conversation_id"])
            if conversation is None:
                raise RuntimeError("Conversation not found")
            if conversation.mode is not ConversationMode.AI:
                return {"response_text": "", "skipped": "human_handoff"}
            try:
                attendance = AiAttendanceService(session).prepare(
                    job["tenant_id"],
                    conversation_id=job["conversation_id"],
                    contact_id=conversation.contact_id,
                    phone=conversation.phone,
                    channel=str(job["channel"]),
                    opening_job_id=job["id"],
                    max_responses=(self.container.settings.commercial_ai_attendance_max_responses),
                )
            except CommercialAllowanceExhausted as exc:
                session.rollback()
                self._handoff_for_allowance(session, job, exc)
                return {
                    "response_text": "",
                    "skipped": "commercial_allowance_exhausted",
                    "commercial_resource": exc.resource,
                }
            self._enrich_media_context(session, job)
            ledger = CreditLedgerService(session)
            reservation = ledger.reserve(
                job["tenant_id"],
                resource="ai_message",
                model=self.container.settings.openai_chat_model,
                estimate=estimated_chat_charge(self.container.settings.openai_chat_model),
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
                    lead_demands=SqlAlchemyLeadDemandRepository(session),
                ).execute(
                    job["tenant_id"],
                    job["conversation_id"],
                    send_to_channel=False,
                    outbound_message_id=job["id"],
                    side_effect_guard=lambda: self._assert_lease(job),
                    dispatch_guard=lambda: self._mark_dispatched(job),
                    usage_observer=lambda response: self._record_accepted_call(job, response),
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
                raise AmbiguousAiCall("Dispatch OpenAI ambíguo; reconciliação necessária") from exc
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
                "response_parts": result.response_parts,
                "model": result.model,
                "tokens_used": result.tokens_used,
                "commercial_attendance_id": str(attendance.session_id),
                "commercial_attendance_new": attendance.is_new_attendance,
            }

    def _enrich_media_context(self, session: Any, job: dict[str, Any]) -> None:
        provider = self.container.ai_provider
        if provider is None:
            return
        messages = session.scalars(
            select(MessageModel)
            .where(
                MessageModel.tenant_id == job["tenant_id"],
                MessageModel.conversation_id == job["conversation_id"],
                MessageModel.direction == "inbound",
                MessageModel.author_type == "customer",
            )
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(25)
        ).all()
        changed = False
        for message in messages:
            enriched: list[dict[str, Any]] = []
            message_changed = False
            for original in message.attachments:
                attachment = dict(original)
                media_type = str(attachment.get("type") or "")
                storage_key = str(attachment.get("storage_key") or "")
                if (
                    media_type not in {"audio", "image"}
                    or not storage_key
                    or attachment.get("ai_status") in {"completed", "failed"}
                ):
                    enriched.append(attachment)
                    continue
                try:
                    content = media_path(
                        self.container.settings.conversation_media_root, storage_key
                    ).read_bytes()
                    content_type = str(attachment.get("mimetype") or "application/octet-stream")
                    if media_type == "audio":
                        text = provider.transcribe_audio(
                            content,
                            filename=str(attachment.get("fileName") or "audio.ogg"),
                            content_type=content_type,
                        )
                        attachment["ai_text"] = (
                            f"[Áudio transcrito]\n{text}"
                            if text
                            else "[Áudio recebido sem fala reconhecível]"
                        )
                        attachment["ai_model"] = self.container.settings.openai_transcription_model
                    else:
                        text = provider.describe_image(content, content_type=content_type)
                        attachment["ai_text"] = (
                            f"[Descrição da imagem]\n{text}"
                            if text
                            else "[Imagem recebida sem descrição disponível]"
                        )
                        attachment["ai_model"] = (
                            self.container.settings.openai_vision_model
                            or self.container.settings.openai_chat_model
                        )
                    attachment["ai_status"] = "completed"
                except Exception:
                    attachment["ai_status"] = "failed"
                    attachment["ai_text"] = (
                        "[Áudio recebido, mas a transcrição não ficou disponível. "
                        "Peça ao cliente que escreva ou reenvie a mensagem.]"
                        if media_type == "audio"
                        else "[Imagem recebida, mas a descrição não ficou disponível. "
                        "Peça ao cliente que explique o que deseja mostrar.]"
                    )
                enriched.append(attachment)
                message_changed = True
            if message_changed:
                message.attachments = enriched
                changed = True
        if changed:
            session.commit()

    def _deliver(self, job: dict[str, Any]) -> dict[str, Any]:
        try:
            with self.container.database.session_factory() as session:
                tenants = SqlAlchemyTenantRepository(session)
                tenant = tenants.get_by_id(job["tenant_id"])
                conversations = SqlAlchemyConversationRepository(session)
                conversation = conversations.get_by_id(job["tenant_id"], job["conversation_id"])
                if tenant is None or conversation is None:
                    raise RuntimeError("Tenant or conversation not found")
                credentials_provider, channel = self._channel(job["channel"])
                credentials = credentials_provider.get(tenant.slug)
                if credentials is None:
                    raise RuntimeError("Canal de mensagens não configurado")
                self._assert_lease(job)
                with self._heartbeat(job):
                    parts = list(job["result"].get("response_parts") or [])
                    if not parts:
                        parts = [job["response_text"]]
                    delivered = dict(job["result"].get("delivered_parts") or {})
                    external_ids: list[str] = []
                    for index, part in enumerate(parts):
                        if str(index) in delivered:
                            external_ids.append(str(delivered[str(index)]))
                            continue
                        delay_ms = min(
                            max(
                                len(part)
                                * self.container.settings.ai_typing_delay_ms_per_character,
                                self.container.settings.ai_typing_delay_min_ms,
                            ),
                            self.container.settings.ai_typing_delay_max_ms,
                        )
                        channel.send_presence(
                            credentials,
                            conversation.phone,
                            delay_ms=delay_ms,
                        )
                        if delay_ms:
                            time.sleep(delay_ms / 1000)
                        sent = channel.send_message(
                            credentials,
                            conversation.phone,
                            part,
                            idempotency_key=(
                                f"{job['id']}:{index}" if job["channel"] == "whatsapp" else None
                            ),
                        )
                        message_id = job["id"] if index == 0 else uuid5(job["id"], str(index))
                        with self.container.database.session_factory() as part_session:
                            MessageJobRepository(part_session).mark_delivery_part(
                                job["id"],
                                job["lease_token"],
                                message_id,
                                index,
                                sent.external_message_id,
                            )
                            attendance_id = job["result"].get("commercial_attendance_id")
                            if attendance_id:
                                AiAttendanceService(part_session).settle_delivery(
                                    job["tenant_id"],
                                    UUID(str(attendance_id)),
                                    delivery_id=job["id"],
                                    window_hours=(
                                        self.container.settings.commercial_ai_attendance_window_hours
                                    ),
                                )
                        external_ids.append(sent.external_message_id)
                        if index < len(parts) - 1:
                            time.sleep(self.container.settings.ai_message_part_pause_ms / 1000)
            with self.container.database.session_factory() as session:
                attendance_id = job["result"].get("commercial_attendance_id")
                if attendance_id:
                    AiAttendanceService(session).settle_delivery(
                        job["tenant_id"],
                        UUID(str(attendance_id)),
                        delivery_id=job["id"],
                        window_hours=(
                            self.container.settings.commercial_ai_attendance_window_hours
                        ),
                    )
                MessageJobRepository(session).finish_delivery(job["id"], job["lease_token"])
            return {
                "id": str(job["id"]),
                "status": "sent",
                "external_message_id": external_ids[-1] if external_ids else None,
                "external_message_ids": external_ids,
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

    def _channel(self, channel_name: str) -> tuple[ChannelCredentialsPort, MessageChannelPort]:
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
            "result": dict(job.result or {}),
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
                    AiAttendanceService(session).touch_for_job(job["tenant_id"], job["id"])

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
            AiAttendanceService(session).touch_for_job(job["tenant_id"], job["id"])

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
            extra = ledger.reservation_extra(job["tenant_id"], self._reservation_key(job["id"]))
            if not extra:
                return
            try:
                charge = chat_charge(
                    str(extra["accepted_model"]),
                    input_tokens=int(extra.get("accepted_input_tokens", 0)),
                    cached_input_tokens=int(extra.get("accepted_cached_input_tokens", 0)),
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
                    "cached_input_tokens": int(extra.get("accepted_cached_input_tokens", 0)),
                    "output_tokens": int(extra.get("accepted_output_tokens", 0)),
                },
            )
            session.commit()

    def _handoff_for_allowance(
        self,
        session: Any,
        job: dict[str, Any],
        error: CommercialAllowanceExhausted,
    ) -> None:
        conversations = SqlAlchemyConversationRepository(session)
        conversation = conversations.get_by_id(job["tenant_id"], job["conversation_id"])
        if conversation is None:
            raise RuntimeError("Conversation not found during commercial handoff")
        conversations.update_mode(
            job["tenant_id"],
            job["conversation_id"],
            ConversationMode.HUMAN,
            None,
            commit=False,
        )
        conversations.record_outbound(
            job["tenant_id"],
            Message(
                tenant_id=job["tenant_id"],
                conversation_id=job["conversation_id"],
                channel=conversation.channel,
                direction=MessageDirection.OUTBOUND,
                author_type=MessageAuthor.SYSTEM,
                text=(
                    "Franquia de atendimentos da IA encerrada. A conversa foi "
                    "encaminhada para a equipe e o cliente não recebeu resposta automática."
                ),
            ),
            commit=False,
        )
        session.commit()
        self.container.event_bus.publish(
            DomainEvent(
                name="HumanHandoffRequested",
                tenant_id=job["tenant_id"],
                payload={
                    "conversation_id": str(job["conversation_id"]),
                    "reason": "commercial_allowance_exhausted",
                    "resource": error.resource,
                },
            )
        )
