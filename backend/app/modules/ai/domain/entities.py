from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class KnowledgeDocumentStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ERROR = "error"


@dataclass(slots=True)
class KnowledgeDocument:
    tenant_id: UUID
    filename: str
    file_type: str
    storage_path: str
    uploaded_by: UUID | None
    id: UUID = field(default_factory=uuid4)
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.PENDING
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    indexed_at: datetime | None = None
    error: str | None = None


@dataclass(slots=True)
class KnowledgeChunk:
    tenant_id: UUID
    document_id: UUID
    content: str
    metadata: dict[str, Any]
    embedding: list[float]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    chunk_id: UUID
    document_id: UUID
    content: str
    metadata: dict[str, Any]
    distance: float


@dataclass(slots=True)
class AiAuditLog:
    tenant_id: UUID
    conversation_id: UUID | None
    input_text: str
    detected_intent: str | None
    tools_called: list[dict[str, Any]]
    chunks_used: list[dict[str, Any]]
    response_text: str
    model: str
    tokens_used: int
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float | None = None
    handoff_reason: str | None = None
    error: str | None = None
    agent_key: str = "leads"
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class AiAgentResult:
    response_text: str
    detected_intent: str | None
    tools_called: list[dict[str, Any]]
    chunks_used: list[dict[str, Any]]
    model: str
    tokens_used: int
    handoff_reason: str | None = None
    response_parts: list[str] = field(default_factory=list)
