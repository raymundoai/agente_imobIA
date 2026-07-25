from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentUploaded:
    tenant_id: UUID
    document_id: UUID


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentIndexed:
    tenant_id: UUID
    document_id: UUID
    chunk_count: int


@dataclass(frozen=True, slots=True)
class AiResponseGenerated:
    tenant_id: UUID
    conversation_id: UUID | None
    audit_log_id: UUID
