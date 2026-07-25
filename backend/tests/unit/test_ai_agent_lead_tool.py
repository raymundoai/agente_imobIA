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
from app.modules.leads.domain.entities import LeadDemand
from app.modules.leads.ports.qualification import LeadQualificationPort
from app.modules.properties.domain.entities import Property
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
                tokens_used=10,
                tool_calls=[
                    AiToolCall(
                        name="create_or_update_lead",
                        arguments={
                            "lead_name": "Maria",
                            "phone": "5511999999999",
                            "email": None,
                            "purpose": "buy",
                            "property_type": "apartamento",
                            "city": "São Paulo",
                            "neighborhoods": ["Pinheiros"],
                            "price_min": 500000,
                            "price_max": 800000,
                            "bedrooms": 2,
                            "parking_spaces": 1,
                            "min_area": None,
                            "notes": "Lead pronto",
                            "handoff_reason": "lead pronto para corretor",
                        },
                    )
                ],
            )
        return AiProviderResponse(text="Encaminhei para um corretor.", model="fake", tokens_used=12)


class FakeLeadQualification(LeadQualificationPort):
    def __init__(self) -> None:
        self.payloads = []

    def create_or_update_lead(self, tenant_id, data, *, conversation_id=None, handoff_reason=None):
        self.payloads.append((tenant_id, data, conversation_id, handoff_reason))
        return LeadDemand(
            tenant_id=tenant_id,
            lead_name=data["lead_name"],
            phone=data["phone"],
            crm_contact_id="contact-1",
            crm_deal_id="deal-1",
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

    def record_outbound(self, tenant_id, message, *, commit=True):
        self.messages.append(message)
        return message

    def update_mode(
        self, tenant_id, conversation_id, mode, assigned_user_id, *, commit=True
    ):
        self.conversation.mode = mode
        return self.conversation


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


def test_ai_agent_create_or_update_lead_tool_uses_port() -> None:
    tenant = Tenant(name="Tenant", slug="tenant-a")
    conversation = Conversation(tenant_id=tenant.id, phone="5511999999999")
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        author_type=MessageAuthor.CUSTOMER,
        text="Quero comprar em Pinheiros",
    )
    qualifier = FakeLeadQualification()

    result = GenerateAiReplyUseCase(
        FakeTenants(tenant),
        FakeConversations(conversation, inbound),
        FakeAi(),
        EmptyKnowledge(),
        FakeAudit(),
        EmptyCredentials(),
        EmptyChannel(),
        InMemoryEventBus(),
        qualifier,
    ).execute(tenant.id, conversation.id)

    assert result.response_text == "Encaminhei para um corretor."
    assert qualifier.payloads[0][0] == tenant.id
    assert qualifier.payloads[0][2] == conversation.id
    assert qualifier.payloads[0][3] == "lead pronto para corretor"
    assert result.tools_called[0]["name"] == "create_or_update_lead"


class PropertySearchAi(AiProviderPort):
    def __init__(self) -> None:
        self.calls = 0
        self.system_prompt = ""

    def get_embedding(self, text: str) -> list[float]:
        return [1.0] * 1536

    def chat_completion(self, *, system_prompt, messages, tools):
        self.calls += 1
        self.system_prompt = system_prompt
        if self.calls == 1:
            return AiProviderResponse(
                text="",
                model="fake",
                tokens_used=5,
                tool_calls=[
                    AiToolCall(
                        name="search_properties",
                        arguments={
                            "city": "São Paulo",
                            "purpose": "buy",
                            "property_type": "apartamento",
                            "neighborhoods": ["Pinheiros"],
                            "price_min": 500000,
                            "price_max": 800000,
                            "bedrooms": 2,
                            "parking_spaces": 1,
                        },
                    )
                ],
            )
        return AiProviderResponse(text="Encontrei uma opção real.", model="fake", tokens_used=7)


class FakeProperties:
    def __init__(self, tenant_id) -> None:
        self.tenant_id = tenant_id
        self.filters = None

    def search_by_filters(self, tenant_id, **filters):
        self.filters = filters
        return [
            Property(
                tenant_id=self.tenant_id,
                source="manual",
                title="Apartamento em Pinheiros",
                city="São Paulo",
            )
        ]


def test_lead_agent_uses_configured_prompt_and_searches_real_properties() -> None:
    tenant = Tenant(
        name="Tenant",
        slug="tenant-a",
        settings={
            "profile": {"display_name": "Imobiliária Teste"},
            "agents": {"leads": {"name": "Consultora Ana", "objective": "qualificar"}},
        },
    )
    conversation = Conversation(tenant_id=tenant.id, phone="5511999999999")
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        author_type=MessageAuthor.CUSTOMER,
        text="Apartamento em Pinheiros até 800 mil",
    )
    ai = PropertySearchAi()
    properties = FakeProperties(tenant.id)

    result = GenerateAiReplyUseCase(
        FakeTenants(tenant),
        FakeConversations(conversation, inbound),
        ai,
        EmptyKnowledge(),
        FakeAudit(),
        EmptyCredentials(),
        EmptyChannel(),
        InMemoryEventBus(),
        properties=properties,
    ).execute(tenant.id, conversation.id)

    assert result.response_text == "Encontrei uma opção real."
    assert result.tokens_used == 12
    assert result.tools_called[0]["name"] == "search_properties"
    assert properties.filters["city"] == "São Paulo"
    assert "Imobiliária Teste" in ai.system_prompt
    assert "Consultora Ana" in ai.system_prompt
