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


def test_agent_does_not_expose_redundant_record_usage_tool() -> None:
    tool_names = {tool["name"] for tool in GenerateAiReplyUseCase._tool_definitions()}

    assert "record_usage" not in tool_names


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


class EmptyThenAnswerAi(AiProviderPort):
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
                tokens_used=20,
                input_tokens=12,
                output_tokens=8,
            )
        assert "retorne obrigatoriamente uma resposta final em texto" in system_prompt
        return AiProviderResponse(
            text="Resposta recuperada",
            model="fake-model",
            tokens_used=9,
            input_tokens=6,
            output_tokens=3,
        )


class ToolLoopAi(AiProviderPort):
    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        return AiProviderResponse(
            text="",
            model="fake-model",
            tokens_used=10,
            tool_calls=[AiToolCall(name="search_knowledge_base", arguments={"query": "faq"})],
        )


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

    def update_mode(
        self, tenant_id, conversation_id, mode, assigned_user_id, *, commit=True
    ):
        self.conversation.mode = mode
        self.conversation.assigned_user_id = assigned_user_id
        return self.conversation


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


def test_ai_agent_retries_one_empty_provider_response_and_aggregates_usage() -> None:
    tenant = Tenant(name="Tenant", slug="tenant-a")
    conversation = Conversation(tenant_id=tenant.id, phone="5511999999999")
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        author_type=MessageAuthor.CUSTOMER,
        text="Qual o horário?",
    )
    ai = EmptyThenAnswerAi()
    audit = FakeAudit()

    result = GenerateAiReplyUseCase(
        FakeTenants(tenant),
        FakeConversations(conversation, inbound),
        ai,
        FakeKnowledge(),
        audit,
        EmptyCredentials(),
        EmptyChannel(),
        InMemoryEventBus(),
    ).execute(tenant.id, conversation.id)

    assert ai.calls == 2
    assert result.response_text == "Resposta recuperada"
    assert result.tokens_used == 29
    assert audit.logs[0].input_tokens == 18
    assert audit.logs[0].output_tokens == 11


def test_ai_agent_hands_off_after_tool_loop_without_final_text() -> None:
    tenant = Tenant(name="Tenant", slug="tenant-a")
    conversation = Conversation(tenant_id=tenant.id, phone="5511999999999")
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        author_type=MessageAuthor.CUSTOMER,
        text="Quero um apartamento",
    )
    conversations = FakeConversations(conversation, inbound)
    audit = FakeAudit()

    result = GenerateAiReplyUseCase(
        FakeTenants(tenant),
        conversations,
        ToolLoopAi(),
        FakeKnowledge(),
        audit,
        EmptyCredentials(),
        EmptyChannel(),
        InMemoryEventBus(),
    ).execute(tenant.id, conversation.id)

    assert result.response_text == (
        "Desculpe, tive um probleminha técnico aqui, mas vou pedir para um humano "
        "seguir com o atendimento."
    )
    assert result.handoff_reason == "technical_response_failure"
    assert conversation.mode.value == "human"
    assert audit.logs[0].error == "ai_response_empty_after_retries"
