from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.modules.ai.domain.entities import (
    AiAuditLog,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSearchResult,
)


@dataclass(frozen=True, slots=True)
class AiToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass(frozen=True, slots=True)
class AiProviderResponse:
    text: str
    model: str
    tokens_used: int
    detected_intent: str | None = None
    tool_calls: list[AiToolCall] | None = None


class AiProviderPort(ABC):
    @abstractmethod
    def get_embedding(self, text: str) -> list[float]:
        raise NotImplementedError

    @abstractmethod
    def chat_completion(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> AiProviderResponse:
        raise NotImplementedError


class KnowledgeDocumentRepositoryPort(ABC):
    @abstractmethod
    def create(self, document: KnowledgeDocument) -> KnowledgeDocument:
        raise NotImplementedError

    @abstractmethod
    def get(self, tenant_id: UUID, document_id: UUID) -> KnowledgeDocument | None:
        raise NotImplementedError

    @abstractmethod
    def list(self, tenant_id: UUID) -> list[KnowledgeDocument]:
        raise NotImplementedError

    @abstractmethod
    def mark_indexing(self, tenant_id: UUID, document_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    def replace_chunks(
        self, tenant_id: UUID, document_id: UUID, chunks: list[KnowledgeChunk]
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def mark_error(self, tenant_id: UUID, document_id: UUID, error: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, tenant_id: UUID, document_id: UUID) -> bool:
        raise NotImplementedError


class KnowledgeSearchPort(ABC):
    @abstractmethod
    def search_by_embedding(
        self, tenant_id: UUID, embedding: list[float], top_k: int
    ) -> list[KnowledgeSearchResult]:
        raise NotImplementedError


class AiAuditLogRepositoryPort(ABC):
    @abstractmethod
    def create(self, audit_log: AiAuditLog) -> AiAuditLog:
        raise NotImplementedError

    @abstractmethod
    def list_for_conversation(self, tenant_id: UUID, conversation_id: UUID) -> list[AiAuditLog]:
        raise NotImplementedError


class DocumentParserPort(ABC):
    @abstractmethod
    def parse(self, filename: str, content: bytes) -> str:
        raise NotImplementedError


class KnowledgeJobQueuePort(ABC):
    @abstractmethod
    def enqueue_index_document(self, tenant_id: UUID, document_id: UUID, content: bytes) -> None:
        raise NotImplementedError
