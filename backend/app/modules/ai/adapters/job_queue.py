from collections.abc import Callable
from uuid import UUID

from app.modules.ai.domain.ports import KnowledgeJobQueuePort


class InProcessKnowledgeJobQueue(KnowledgeJobQueuePort):
    def __init__(self, handler: Callable[[UUID, UUID, bytes], None] | None = None) -> None:
        self._handler = handler
        self.jobs: list[tuple[UUID, UUID, bytes]] = []

    def enqueue_index_document(self, tenant_id: UUID, document_id: UUID, content: bytes) -> None:
        self.jobs.append((tenant_id, document_id, content))
        if self._handler is not None:
            self._handler(tenant_id, document_id, content)
