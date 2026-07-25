import base64
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.ai.adapters.job_queue import InProcessKnowledgeJobQueue
from app.modules.ai.adapters.repositories import (
    SqlAlchemyAiAuditLogRepository,
    SqlAlchemyKnowledgeRepository,
)
from app.modules.ai.application.use_cases import (
    DeleteKnowledgeDocumentUseCase,
    GenerateAiReplyUseCase,
    ProcessKnowledgeDocumentUseCase,
    SearchKnowledgeUseCase,
    UploadKnowledgeDocumentInput,
    UploadKnowledgeDocumentUseCase,
)
from app.modules.ai.domain.entities import KnowledgeDocument
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.billing_usage.service import CreditLedgerService
from app.modules.conversations.adapters.repositories import SqlAlchemyConversationRepository
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.application.use_cases import LeadQualificationService
from app.modules.properties.adapters.repositories import SqlAlchemyPropertyRepository
from app.modules.tenants.adapters.repositories import SqlAlchemyTenantRepository
from app.shared.errors.exceptions import ConfigurationError, NotFoundError

knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])
ai_router = APIRouter(prefix="/ai", tags=["ai"])


class UploadKnowledgeDocumentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    file_type: str = Field(min_length=1, max_length=80)
    content_base64: str = Field(min_length=1)


class ReindexKnowledgeDocumentRequest(BaseModel):
    content_base64: str = Field(min_length=1)


class KnowledgeDocumentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    filename: str
    file_type: str
    storage_path: str
    status: str
    version: int
    uploaded_by: UUID | None
    error: str | None

    @classmethod
    def from_domain(cls, document: KnowledgeDocument) -> "KnowledgeDocumentResponse":
        return cls(
            id=document.id,
            tenant_id=document.tenant_id,
            filename=document.filename,
            file_type=document.file_type,
            storage_path=document.storage_path,
            status=document.status.value,
            version=document.version,
            uploaded_by=document.uploaded_by,
            error=document.error,
        )


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)


class KnowledgeSearchResponse(BaseModel):
    results: list[dict[str, Any]]


class AiReplyRequest(BaseModel):
    input_text: str | None = None
    send_to_channel: bool = False


class AiReplyResponse(BaseModel):
    response_text: str
    detected_intent: str | None
    tools_called: list[dict[str, Any]]
    chunks_used: list[dict[str, Any]]
    model: str
    tokens_used: int
    handoff_reason: str | None


@knowledge_router.post(
    "/documents", response_model=KnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED
)
def upload_document(
    payload: UploadKnowledgeDocumentRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> KnowledgeDocumentResponse:
    ai_provider = _ai_provider(container)
    repository = SqlAlchemyKnowledgeRepository(session)

    def process(tenant_id: UUID, document_id: UUID, content: bytes) -> None:
        ProcessKnowledgeDocumentUseCase(
            repository,
            container.document_parser,
            ai_provider,
            container.event_bus,
        ).execute(tenant_id, document_id, content)

    document = UploadKnowledgeDocumentUseCase(
        repository,
        InProcessKnowledgeJobQueue(process),
        container.event_bus,
    ).execute(
        UploadKnowledgeDocumentInput(
            tenant_id=principal.tenant_id,
            filename=payload.filename,
            file_type=payload.file_type,
            content=base64.b64decode(payload.content_base64),
            uploaded_by=principal.user_id,
        )
    )
    document = repository.get(principal.tenant_id, document.id) or document
    return KnowledgeDocumentResponse.from_domain(document)


@knowledge_router.get("/documents", response_model=list[KnowledgeDocumentResponse])
def list_documents(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[KnowledgeDocumentResponse]:
    return [
        KnowledgeDocumentResponse.from_domain(document)
        for document in SqlAlchemyKnowledgeRepository(session).list(principal.tenant_id)
    ]


@knowledge_router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> None:
    DeleteKnowledgeDocumentUseCase(SqlAlchemyKnowledgeRepository(session)).execute(
        principal.tenant_id, document_id
    )


@knowledge_router.post("/documents/{document_id}/reindex", response_model=KnowledgeDocumentResponse)
def reindex_document(
    document_id: UUID,
    payload: ReindexKnowledgeDocumentRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> KnowledgeDocumentResponse:
    repository = SqlAlchemyKnowledgeRepository(session)
    document = repository.get(principal.tenant_id, document_id)
    if document is None:
        raise NotFoundError("Knowledge document not found")
    ProcessKnowledgeDocumentUseCase(
        repository,
        container.document_parser,
        _ai_provider(container),
        container.event_bus,
    ).execute(principal.tenant_id, document_id, base64.b64decode(payload.content_base64))
    refreshed = repository.get(principal.tenant_id, document_id)
    if refreshed is None:
        raise NotFoundError("Knowledge document not found")
    return KnowledgeDocumentResponse.from_domain(refreshed)


@knowledge_router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    payload: KnowledgeSearchRequest,
    top_k: Annotated[int, Query(ge=1, le=20)] = 5,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> KnowledgeSearchResponse:
    results = SearchKnowledgeUseCase(
        _ai_provider(container), SqlAlchemyKnowledgeRepository(session)
    ).execute(principal.tenant_id, payload.query, top_k)
    return KnowledgeSearchResponse(results=results)


@ai_router.post("/conversations/{conversation_id}/respond", response_model=AiReplyResponse)
def generate_ai_reply(
    conversation_id: UUID,
    payload: AiReplyRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> AiReplyResponse:
    CreditLedgerService(session).ensure_available(principal.tenant_id, resource="ai_message")
    result = GenerateAiReplyUseCase(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyConversationRepository(session),
        _ai_provider(container),
        SqlAlchemyKnowledgeRepository(session),
        SqlAlchemyAiAuditLogRepository(session),
        container.channel_credentials,
        container.message_channel,
        container.event_bus,
        LeadQualificationService(
            SqlAlchemyTenantRepository(session),
            SqlAlchemyLeadDemandRepository(session),
            container.crm_credentials,
            container.crm,
            container.event_bus,
        ),
        properties=SqlAlchemyPropertyRepository(session),
    ).execute(
        principal.tenant_id,
        conversation_id,
        payload.input_text,
        send_to_channel=payload.send_to_channel,
    )
    return AiReplyResponse(
        response_text=result.response_text,
        detected_intent=result.detected_intent,
        tools_called=result.tools_called,
        chunks_used=result.chunks_used,
        model=result.model,
        tokens_used=result.tokens_used,
        handoff_reason=result.handoff_reason,
    )


def _ai_provider(container: Container):
    if container.ai_provider is None:
        raise ConfigurationError("OpenAI integration is not configured")
    return container.ai_provider
