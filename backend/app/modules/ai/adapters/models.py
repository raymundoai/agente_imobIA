from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.shared.database.base import Base


class Vector1536(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_: object) -> str:
        return "vector(1536)"


class KnowledgeDocumentModel(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'indexing', 'indexed', 'error')", name="status"),
        ForeignKeyConstraint(
            ["tenant_id", "uploaded_by"],
            ["users.tenant_id", "users.id"],
            name="fk_knowledge_documents_tenant_uploaded_by",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_documents_tenant_id_id"),
        Index("ix_knowledge_documents_tenant_status", "tenant_id", "status"),
        Index("ix_knowledge_documents_tenant_created", "tenant_id", sql_text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_knowledge_documents_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    uploaded_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeChunkModel(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_knowledge_chunks_tenant_document",
            ondelete="CASCADE",
        ),
        Index("ix_knowledge_chunks_tenant_document", "tenant_id", "document_id"),
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    embedding: Mapped[Any] = mapped_column(Vector1536(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AiAuditLogModel(Base):
    __tablename__ = "ai_audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_ai_audit_logs_tenant_conversation",
            ondelete="CASCADE",
        ),
        Index("ix_ai_audit_logs_tenant_created", "tenant_id", sql_text("created_at DESC")),
        Index(
            "ix_ai_audit_logs_tenant_conversation",
            "tenant_id",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_ai_audit_logs_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    detected_intent: Mapped[str | None] = mapped_column(Text)
    tools_called: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )
    chunks_used: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    handoff_reason: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    agent_key: Mapped[str] = mapped_column(
        Text, nullable=False, default="leads", server_default="leads"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
