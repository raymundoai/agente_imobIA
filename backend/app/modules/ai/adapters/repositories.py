from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.modules.ai.adapters.models import (
    AiAuditLogModel,
    KnowledgeChunkModel,
    KnowledgeDocumentModel,
)
from app.modules.ai.domain.entities import (
    AiAuditLog,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSearchResult,
)
from app.modules.ai.domain.ports import (
    AiAuditLogRepositoryPort,
    KnowledgeDocumentRepositoryPort,
    KnowledgeSearchPort,
)
from app.modules.billing_usage.adapters.models import UsageRecordModel
from app.modules.billing_usage.service import CreditLedgerService, chat_charge


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.12g}" for value in values) + "]"


def _document_to_domain(model: KnowledgeDocumentModel) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=model.id,
        tenant_id=model.tenant_id,
        filename=model.filename,
        file_type=model.file_type,
        storage_path=model.storage_path,
        status=KnowledgeDocumentStatus(model.status),
        version=model.version,
        uploaded_by=model.uploaded_by,
        created_at=model.created_at,
        indexed_at=model.indexed_at,
        error=model.error,
    )


def _audit_to_domain(model: AiAuditLogModel) -> AiAuditLog:
    return AiAuditLog(
        id=model.id,
        tenant_id=model.tenant_id,
        conversation_id=model.conversation_id,
        input_text=model.input_text,
        detected_intent=model.detected_intent,
        tools_called=model.tools_called,
        chunks_used=model.chunks_used,
        response_text=model.response_text,
        model=model.model,
        tokens_used=model.tokens_used,
        estimated_cost=model.estimated_cost,
        handoff_reason=model.handoff_reason,
        error=model.error,
        agent_key=model.agent_key,
        created_at=model.created_at,
    )


class SqlAlchemyKnowledgeRepository(KnowledgeDocumentRepositoryPort, KnowledgeSearchPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, document: KnowledgeDocument) -> KnowledgeDocument:
        model = KnowledgeDocumentModel(
            id=document.id,
            tenant_id=document.tenant_id,
            filename=document.filename,
            file_type=document.file_type,
            storage_path=document.storage_path,
            status=document.status.value,
            version=document.version,
            uploaded_by=document.uploaded_by,
            created_at=document.created_at,
            indexed_at=document.indexed_at,
            error=document.error,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _document_to_domain(model)

    def get(self, tenant_id: UUID, document_id: UUID) -> KnowledgeDocument | None:
        model = self._session.scalar(
            select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.tenant_id == tenant_id,
                KnowledgeDocumentModel.id == document_id,
            )
        )
        return _document_to_domain(model) if model else None

    def list(self, tenant_id: UUID) -> list[KnowledgeDocument]:
        models = self._session.scalars(
            select(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.tenant_id == tenant_id)
            .order_by(KnowledgeDocumentModel.created_at.desc(), KnowledgeDocumentModel.id)
        ).all()
        return [_document_to_domain(model) for model in models]

    def mark_indexing(self, tenant_id: UUID, document_id: UUID) -> None:
        model = self._locked_document(tenant_id, document_id)
        if model is None:
            return
        model.status = KnowledgeDocumentStatus.INDEXING.value
        model.error = None
        self._session.commit()

    def replace_chunks(
        self, tenant_id: UUID, document_id: UUID, chunks: list[KnowledgeChunk]
    ) -> None:
        model = self._locked_document(tenant_id, document_id)
        if model is None:
            return
        self._session.execute(
            delete(KnowledgeChunkModel).where(
                KnowledgeChunkModel.tenant_id == tenant_id,
                KnowledgeChunkModel.document_id == document_id,
            )
        )
        for chunk in chunks:
            self._session.execute(
                text(
                    """
                    INSERT INTO knowledge_chunks
                      (id, tenant_id, document_id, content, metadata, embedding, created_at)
                    VALUES
                      (:id, :tenant_id, :document_id, :content, CAST(:metadata AS jsonb),
                       CAST(:embedding AS vector), :created_at)
                    """
                ),
                {
                    "id": chunk.id,
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "content": chunk.content,
                    "metadata": json.dumps(chunk.metadata),
                    "embedding": _vector_literal(chunk.embedding),
                    "created_at": chunk.created_at,
                },
            )
        model.status = KnowledgeDocumentStatus.INDEXED.value
        model.indexed_at = datetime.now(UTC)
        model.error = None
        self._session.commit()

    def mark_error(self, tenant_id: UUID, document_id: UUID, error: str) -> None:
        model = self._locked_document(tenant_id, document_id)
        if model is None:
            return
        model.status = KnowledgeDocumentStatus.ERROR.value
        model.error = error[:2000]
        self._session.commit()

    def delete(self, tenant_id: UUID, document_id: UUID) -> bool:
        model = self._locked_document(tenant_id, document_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.commit()
        return True

    def search_by_embedding(
        self, tenant_id: UUID, embedding: list[float], top_k: int
    ) -> list[KnowledgeSearchResult]:
        rows = self._session.execute(
            text(
                """
                SELECT id, document_id, content, metadata,
                       embedding <=> CAST(:embedding AS vector) AS distance
                FROM knowledge_chunks
                WHERE tenant_id = :tenant_id
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
                """
            ),
            {"tenant_id": tenant_id, "embedding": _vector_literal(embedding), "top_k": top_k},
        ).mappings()
        return [
            KnowledgeSearchResult(
                chunk_id=row["id"],
                document_id=row["document_id"],
                content=row["content"],
                metadata=row["metadata"],
                distance=float(row["distance"]),
            )
            for row in rows
        ]

    def _locked_document(self, tenant_id: UUID, document_id: UUID) -> KnowledgeDocumentModel | None:
        return self._session.scalar(
            select(KnowledgeDocumentModel)
            .where(
                KnowledgeDocumentModel.tenant_id == tenant_id,
                KnowledgeDocumentModel.id == document_id,
            )
            .with_for_update()
        )


class SqlAlchemyAiAuditLogRepository(AiAuditLogRepositoryPort):
    def __init__(
        self, session: Session, *, credit_reservation_key: str | None = None
    ) -> None:
        self._session = session
        self._credit_reservation_key = credit_reservation_key

    def create(self, audit_log: AiAuditLog) -> AiAuditLog:
        try:
            charge = chat_charge(
                audit_log.model,
                input_tokens=audit_log.input_tokens,
                cached_input_tokens=audit_log.cached_input_tokens,
                output_tokens=audit_log.output_tokens,
            )
        except ValueError:
            if self._credit_reservation_key is not None:
                if audit_log.model == "guardrail":
                    CreditLedgerService(self._session).release_reservation(
                        audit_log.tenant_id,
                        self._credit_reservation_key,
                        commit=False,
                    )
                else:
                    raise
            charge = None
        if charge is not None:
            audit_log.estimated_cost = float(charge.provider_cost_usd)
        model = AiAuditLogModel(
            id=audit_log.id,
            tenant_id=audit_log.tenant_id,
            conversation_id=audit_log.conversation_id,
            input_text=audit_log.input_text,
            detected_intent=audit_log.detected_intent,
            tools_called=audit_log.tools_called,
            chunks_used=audit_log.chunks_used,
            response_text=audit_log.response_text,
            model=audit_log.model,
            tokens_used=audit_log.tokens_used,
            estimated_cost=audit_log.estimated_cost,
            handoff_reason=audit_log.handoff_reason,
            error=audit_log.error,
            agent_key=audit_log.agent_key,
            created_at=audit_log.created_at,
        )
        self._session.add(model)
        self._session.add(
            UsageRecordModel(
                id=uuid4(),
                tenant_id=audit_log.tenant_id,
                type="ai_call",
                quantity=1,
                module="ai",
                related_entity_id=audit_log.id,
                estimated_cost=audit_log.estimated_cost,
            )
        )
        if charge is not None and self._credit_reservation_key is not None:
            CreditLedgerService(self._session).settle_reservation(
                audit_log.tenant_id,
                idempotency_key=self._credit_reservation_key,
                model=audit_log.model,
                charge=charge,
                reference_id=audit_log.id,
                extra={
                    "input_tokens": audit_log.input_tokens,
                    "cached_input_tokens": audit_log.cached_input_tokens,
                    "output_tokens": audit_log.output_tokens,
                },
            )
        elif charge is not None:
            CreditLedgerService(self._session).consume(
                audit_log.tenant_id,
                resource="ai_message",
                model=audit_log.model,
                charge=charge,
                idempotency_key=f"ai:{audit_log.id}",
                reference_id=audit_log.id,
                extra={
                    "input_tokens": audit_log.input_tokens,
                    "cached_input_tokens": audit_log.cached_input_tokens,
                    "output_tokens": audit_log.output_tokens,
                },
            )
        self._session.commit()
        self._session.refresh(model)
        return _audit_to_domain(model)

    def list_for_conversation(self, tenant_id: UUID, conversation_id: UUID) -> list[AiAuditLog]:
        models = self._session.scalars(
            select(AiAuditLogModel)
            .where(
                AiAuditLogModel.tenant_id == tenant_id,
                AiAuditLogModel.conversation_id == conversation_id,
            )
            .order_by(AiAuditLogModel.created_at, AiAuditLogModel.id)
        ).all()
        return [_audit_to_domain(model) for model in models]
