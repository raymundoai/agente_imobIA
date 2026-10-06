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


class AiProviderRejectedError(RuntimeError):
    """The provider definitively rejected the request before billable acceptance."""


class AiProviderDispatchUncertainError(RuntimeError):
    """The request may have reached the provider and requires reconciliation."""


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
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    detected_intent: str | None = None
    tool_calls: list[AiToolCall] | None = None


@dataclass(frozen=True, slots=True)
class ChatOptions:
    """Per-call overrides of the server's chat defaults; None keeps the default."""

    model: str | None = None
    reasoning_effort: str | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    """Platform-managed agent settings; None falls back to the built-in prompt and defaults."""

    base_prompt: str | None = None
    extra_instructions: str | None = None
    chat_model: str | None = None
    reasoning_effort: str | None = None
    max_output_tokens: int | None = None

    def chat_options(self) -> ChatOptions | None:
        if not (self.chat_model or self.reasoning_effort or self.max_output_tokens):
            return None
        return ChatOptions(self.chat_model, self.reasoning_effort, self.max_output_tokens)


class AgentConfigPort(ABC):
    @abstractmethod
    def for_tenant(self, tenant_id: UUID) -> AgentRuntimeConfig:
        raise NotImplementedError


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
        options: ChatOptions | None = None,
    ) -> AiProviderResponse:
        raise NotImplementedError

    def transcribe_audio(self, content: bytes, *, filename: str, content_type: str) -> str:
        raise NotImplementedError("This AI provider does not support audio transcription")

    def describe_image(self, content: bytes, *, content_type: str) -> str:
        raise NotImplementedError("This AI provider does not support image understanding")


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
