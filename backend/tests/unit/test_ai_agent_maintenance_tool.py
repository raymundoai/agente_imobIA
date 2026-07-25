from app.modules.ai.application.use_cases import GenerateAiReplyUseCase
from app.modules.ai.domain.entities import AiAuditLog
from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse, AiToolCall
from app.modules.conversations.domain.entities import (
    Conversation,
    Message,
    MessageAuthor,
    MessageDirection,
)
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.maintenance.domain.entities import MaintenanceTicket, MaintenanceUrgency
from app.modules.maintenance.ports.ticketing import MaintenanceTicketingPort
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
                model="fake",
                tokens_used=8,
                tool_calls=[
                    AiToolCall(
                        name="create_maintenance_ticket",
                        arguments={
                            "customer_name": "Ana",
                            "phone": "5511999999999",
                            "property_reference": "Apto 12",
                            "issue_type": "vazamento",
                            "description": "Vazamento forte na cozinha",
                            "urgency": "high",
                            "attachments": [],
                        },
                    )
                ],
            )
        return AiProviderResponse(text="Chamado aberto.", model="fake", tokens_used=11)


class FakeMaintenance(MaintenanceTicketingPort):
    def __init__(self) -> None:
        self.payloads = []

    def create_ticket(self, tenant_id, data, *, conversation_id=None):
        self.payloads.append((tenant_id, data, conversation_id))
        return MaintenanceTicket(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            customer_name=data["customer_name"],
            phone=data["phone"],
            issue_type=data["issue_type"],
            description=data["description"],
            urgency=MaintenanceUrgency.HIGH,
        )


class FakeTenants:
    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant

    def get_by_id(self, tenant_id):
        return self.tenant if tenant_id == self.tenant.id else None


class FakeConversations:
    def __init__(self, conversation: Conversation, inbound: Message) -> None:
        self.conversation = conversation
        self.messages = [inbound]

    def get_by_id(self, tenant_id, conversation_id):
        return self.conversation if tenant_id == self.conversation.tenant_id else None

    def list_messages(self, tenant_id, conversation_id):
        return self.messages

    def record_outbound(self, tenant_id, message):
        self.messages.append(message)
        return message


class EmptyKnowledge:
    def search_by_embedding(self, tenant_id, embedding, top_k):
        return []


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


def test_ai_agent_create_maintenance_ticket_tool_uses_port() -> None:
    tenant = Tenant(name="Tenant", slug="tenant-a")
    conversation = Conversation(tenant_id=tenant.id, phone="5511999999999")
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        author_type=MessageAuthor.CUSTOMER,
        text="Tenho vazamento na cozinha",
    )
    maintenance = FakeMaintenance()

    result = GenerateAiReplyUseCase(
        FakeTenants(tenant),
        FakeConversations(conversation, inbound),
        FakeAi(),
        EmptyKnowledge(),
        FakeAudit(),
        EmptyCredentials(),
        EmptyChannel(),
        InMemoryEventBus(),
        maintenance_ticketing=maintenance,
    ).execute(tenant.id, conversation.id)

    assert result.response_text == "Chamado aberto."
    assert result.tools_called[0]["name"] == "create_maintenance_ticket"
    assert maintenance.payloads[0][0] == tenant.id
    assert maintenance.payloads[0][2] == conversation.id
