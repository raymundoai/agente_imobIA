from uuid import uuid4

from app.modules.ai.application.use_cases import GenerateAiReplyUseCase
from app.modules.ai.domain.entities import AiAuditLog, KnowledgeSearchResult
from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse, AiToolCall
from app.modules.conversations.domain.entities import (
    Conversation,
    Message,
    MessageAuthor,
    MessageDirection,
)
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.tenants.domain.entities import Tenant
from app.shared.events.in_memory import InMemoryEventBus


class FakeAi(AiProviderPort):
    def __init__(self) -> None:
        self.calls = 0

    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return AiProviderResponse(
                text="",
                model="fake-model",
                tokens_used=10,
                tool_calls=[AiToolCall(name="search_knowledge_base", arguments={"query": "faq"})],
            )
        return AiProviderResponse(text="Resposta final", model="fake-model", tokens_used=15)


class FakeTenants:
    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant

    def get_by_id(self, tenant_id):
        return self.tenant if self.tenant.id == tenant_id else None


class FakeConversations:
    def __init__(self, conversation: Conversation, inbound: Message) -> None:
        self.conversation = conversation
        self.messages = [inbound]

    def get_by_id(self, tenant_id, conversation_id):
        return self.conversation if self.conversation.tenant_id == tenant_id else None

    def list_messages(self, tenant_id, conversation_id):
        return list(self.messages)

    def record_outbound(self, tenant_id, message, *, commit=True):
        self.messages.append(message)
        return message


class FakeKnowledge:
    def search_by_embedding(self, tenant_id, embedding, top_k):
        return [
            KnowledgeSearchResult(
                chunk_id=uuid4(),
                document_id=uuid4(),
                content="FAQ do tenant",
                metadata={},
                distance=0.1,
            )
        ]


class FakeAudit:
    def __init__(self) -> None:
        self.logs: list[AiAuditLog] = []

    def create(self, audit_log):
        self.logs.append(audit_log)
        return audit_log

    def list_for_conversation(self, tenant_id, conversation_id):
        return self.logs


class EmptyCredentials(ChannelCredentialsPort):
    def get(self, tenant_slug):
        return None


class EmptyChannel(MessageChannelPort):
    def receive_message(self, payload):
        raise NotImplementedError

    def send_message(self, credentials, phone, text):
        raise NotImplementedError


def test_ai_agent_executes_tool_and_records_audit_log() -> None:
    tenant = Tenant(name="Tenant", slug="tenant-a", settings={"tom_de_voz": "objetivo"})
    conversation = Conversation(tenant_id=tenant.id, phone="5511999999999")
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        author_type=MessageAuthor.CUSTOMER,
        text="Qual o horário?",
    )
    audit = FakeAudit()

    result = GenerateAiReplyUseCase(
        FakeTenants(tenant),
        FakeConversations(conversation, inbound),
        FakeAi(),
        FakeKnowledge(),
        audit,
        EmptyCredentials(),
        EmptyChannel(),
        InMemoryEventBus(),
    ).execute(tenant.id, conversation.id)

    assert result.response_text == "Resposta final"
    assert result.tools_called == [{"name": "search_knowledge_base", "arguments": {"query": "faq"}}]
    assert audit.logs[0].tenant_id == tenant.id
    assert audit.logs[0].chunks_used
