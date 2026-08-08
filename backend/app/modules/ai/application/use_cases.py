import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4, uuid5

from app.modules.ai.application.guardrails import detect_restricted_intent
from app.modules.ai.domain.entities import (
    AiAgentResult,
    AiAuditLog,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.modules.ai.domain.ports import (
    AiAuditLogRepositoryPort,
    AiProviderPort,
    AiProviderResponse,
    DocumentParserPort,
    KnowledgeDocumentRepositoryPort,
    KnowledgeJobQueuePort,
    KnowledgeSearchPort,
)
from app.modules.conversations.domain.entities import (
    ConversationMode,
    Message,
    MessageAuthor,
    MessageDirection,
)
from app.modules.conversations.ports.repositories import ConversationRepositoryPort
from app.modules.integrations.ports.credentials import ChannelCredentialsPort
from app.modules.integrations.ports.message_channel import MessageChannelPort
from app.modules.leads.ports.qualification import LeadQualificationPort
from app.modules.leads.ports.repositories import LeadDemandRepositoryPort
from app.modules.properties.ports.repositories import PropertyRepositoryPort
from app.modules.tenants.domain.entities import TenantStatus
from app.modules.tenants.ports.repositories import TenantRepositoryPort
from app.shared.errors.exceptions import ConfigurationError, NotFoundError
from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort


@dataclass(frozen=True, slots=True)
class UploadKnowledgeDocumentInput:
    tenant_id: UUID
    filename: str
    file_type: str
    content: bytes
    uploaded_by: UUID | None


class UploadKnowledgeDocumentUseCase:
    def __init__(
        self,
        documents: KnowledgeDocumentRepositoryPort,
        jobs: KnowledgeJobQueuePort,
        events: EventBusPort,
    ) -> None:
        self._documents = documents
        self._jobs = jobs
        self._events = events

    def execute(self, data: UploadKnowledgeDocumentInput) -> KnowledgeDocument:
        document = self._documents.create(
            KnowledgeDocument(
                tenant_id=data.tenant_id,
                filename=data.filename,
                file_type=data.file_type,
                storage_path=f"inline://{data.filename}",
                uploaded_by=data.uploaded_by,
            )
        )
        self._events.publish(
            DomainEvent(
                name="KnowledgeDocumentUploaded",
                tenant_id=data.tenant_id,
                payload={"document_id": str(document.id)},
            )
        )
        self._jobs.enqueue_index_document(data.tenant_id, document.id, data.content)
        return document


class ProcessKnowledgeDocumentUseCase:
    def __init__(
        self,
        documents: KnowledgeDocumentRepositoryPort,
        parser: DocumentParserPort,
        ai: AiProviderPort,
        events: EventBusPort,
        *,
        chunk_size_words: int = 500,
        overlap_words: int = 50,
        max_words: int = 50_000,
    ) -> None:
        self._documents = documents
        self._parser = parser
        self._ai = ai
        self._events = events
        self._chunk_size_words = chunk_size_words
        self._overlap_words = overlap_words
        self._max_words = max_words

    def execute(self, tenant_id: UUID, document_id: UUID, content: bytes) -> int:
        document = self._documents.get(tenant_id, document_id)
        if document is None:
            raise NotFoundError("Knowledge document not found")
        self._documents.mark_indexing(tenant_id, document_id)
        try:
            text = self._parser.parse(document.filename, content)
            chunks = [
                KnowledgeChunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    content=chunk,
                    metadata={
                        "filename": document.filename,
                        "file_type": document.file_type,
                        "chunk_index": index,
                        "version": document.version,
                    },
                    embedding=self._ai.get_embedding(chunk),
                )
                for index, chunk in enumerate(self._chunk_text(text))
            ]
            self._documents.replace_chunks(tenant_id, document_id, chunks)
            self._events.publish(
                DomainEvent(
                    name="KnowledgeDocumentIndexed",
                    tenant_id=tenant_id,
                    payload={"document_id": str(document_id), "chunk_count": len(chunks)},
                )
            )
            return len(chunks)
        except Exception as exc:
            self._documents.mark_error(tenant_id, document_id, str(exc))
            raise

    def _chunk_text(self, text: str) -> list[str]:
        words = text.split()
        if not words:
            return []
        if len(words) > self._max_words:
            raise ValueError(
                "Documento muito extenso; reduza-o para no máximo 50 mil palavras"
            )
        chunks: list[str] = []
        step = max(1, self._chunk_size_words - self._overlap_words)
        for start in range(0, len(words), step):
            part = words[start : start + self._chunk_size_words]
            if part:
                chunks.append(" ".join(part))
            if start + self._chunk_size_words >= len(words):
                break
        return chunks


class SearchKnowledgeUseCase:
    def __init__(self, ai: AiProviderPort, search: KnowledgeSearchPort) -> None:
        self._ai = ai
        self._search = search

    def execute(self, tenant_id: UUID, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        embedding = self._ai.get_embedding(query)
        return [
            {
                "chunk_id": str(result.chunk_id),
                "document_id": str(result.document_id),
                "content": result.content,
                "metadata": result.metadata,
                "distance": result.distance,
            }
            for result in self._search.search_by_embedding(tenant_id, embedding, top_k)
        ]


class DeleteKnowledgeDocumentUseCase:
    def __init__(self, documents: KnowledgeDocumentRepositoryPort) -> None:
        self._documents = documents

    def execute(self, tenant_id: UUID, document_id: UUID) -> None:
        if not self._documents.delete(tenant_id, document_id):
            raise NotFoundError("Knowledge document not found")


class GenerateAiReplyUseCase:
    def __init__(
        self,
        tenants: TenantRepositoryPort,
        conversations: ConversationRepositoryPort,
        ai: AiProviderPort,
        knowledge: KnowledgeSearchPort,
        audit_logs: AiAuditLogRepositoryPort,
        credentials: ChannelCredentialsPort,
        channel: MessageChannelPort,
        events: EventBusPort,
        lead_qualification: LeadQualificationPort | None = None,
        properties: PropertyRepositoryPort | None = None,
        lead_demands: LeadDemandRepositoryPort | None = None,
    ) -> None:
        self._tenants = tenants
        self._conversations = conversations
        self._ai = ai
        self._knowledge = knowledge
        self._audit_logs = audit_logs
        self._credentials = credentials
        self._channel = channel
        self._events = events
        self._lead_qualification = lead_qualification
        self._properties = properties
        self._lead_demands = lead_demands

    def execute(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        input_text: str | None = None,
        *,
        send_to_channel: bool = False,
        outbound_message_id: UUID | None = None,
        side_effect_guard: Callable[[], None] | None = None,
        dispatch_guard: Callable[[], None] | None = None,
        usage_observer: Callable[[AiProviderResponse], None] | None = None,
    ) -> AiAgentResult:
        tenant = self._tenants.get_by_id(tenant_id)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            raise NotFoundError("Tenant not found")
        leads_settings = (tenant.settings.get("agents") or {}).get("leads") or {}
        if str(leads_settings.get("status", "active")).lower() == "inactive":
            raise ConfigurationError("Agente de qualificação está inativo")
        conversation = self._conversations.get_by_id(tenant_id, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        if conversation.mode is not ConversationMode.AI:
            raise ConfigurationError("AI is disabled while the conversation is in human mode")
        agent_key, agent_settings = self._resolve_agent(tenant.settings)
        history = self._conversations.list_messages(tenant_id, conversation_id)[-25:]
        user_text = input_text or next(
            (message.text for message in reversed(history) if message.direction.value == "inbound"),
            "",
        )
        restricted_reason = detect_restricted_intent(user_text)
        if restricted_reason:
            return self._handoff_for_restricted_intent(
                tenant_id,
                conversation_id,
                user_text,
                restricted_reason,
                send_to_channel=send_to_channel,
                tenant_slug=tenant.slug,
                phone=conversation.phone,
                channel=conversation.channel,
                outbound_message_id=outbound_message_id,
                side_effect_guard=side_effect_guard,
            )
        query_embedding = self._ai.get_embedding(user_text)
        chunks = self._knowledge.search_by_embedding(tenant_id, query_embedding, 5)
        chunks_used = [
            {
                "chunk_id": str(chunk.chunk_id),
                "document_id": str(chunk.document_id),
                "distance": chunk.distance,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ]
        if dispatch_guard is not None:
            dispatch_guard()
        response = self._ai.chat_completion(
            system_prompt=self._system_prompt(
                tenant.settings,
                agent_key,
                agent_settings,
                chunks,
                self._conversation_context(tenant_id, conversation),
            ),
            messages=self._messages_from_history(history),
            tools=self._tool_definitions(agent_key),
        )
        if usage_observer is not None:
            usage_observer(response)
        tools_called: list[dict[str, Any]] = []
        handoff_reason: str | None = None
        tool_context: list[dict[str, str]] = []
        total_tokens = response.tokens_used
        input_tokens = response.input_tokens
        cached_input_tokens = response.cached_input_tokens
        output_tokens = response.output_tokens
        tool_iterations = 0
        empty_response_retried = False
        while True:
            if response.tool_calls:
                if tool_iterations >= 4:
                    break
                tool_iterations += 1
                tool_outputs: list[dict[str, str]] = []
                for call in response.tool_calls:
                    if side_effect_guard is not None:
                        side_effect_guard()
                    output = self._execute_tool(
                        call.name, call.arguments, tenant_id, conversation_id
                    )
                    tools_called.append({"name": call.name, "arguments": call.arguments})
                    if call.name == "request_human_handoff":
                        handoff_reason = str(call.arguments.get("reason") or "ai_requested")
                    tool_outputs.append(
                        {
                            "role": "tool",
                            "name": call.name,
                            "content": json.dumps(output, ensure_ascii=False),
                        }
                    )
                tool_context.extend(tool_outputs)
                retry_instruction = ""
            elif not response.text.strip() and not empty_response_retried:
                empty_response_retried = True
                retry_instruction = (
                    "\n\nNesta tentativa, retorne obrigatoriamente uma resposta final em texto "
                    "para o cliente. Não encerre apenas com raciocínio interno."
                )
            else:
                break
            if dispatch_guard is not None:
                dispatch_guard()
            response = self._ai.chat_completion(
                system_prompt=self._system_prompt(
                    tenant.settings,
                    agent_key,
                    agent_settings,
                    chunks,
                    self._conversation_context(tenant_id, conversation),
                )
                + retry_instruction,
                messages=[*self._messages_from_history(history), *tool_context],
                tools=self._tool_definitions(agent_key),
            )
            if usage_observer is not None:
                usage_observer(response)
            total_tokens += response.tokens_used
            input_tokens += response.input_tokens
            cached_input_tokens += response.cached_input_tokens
            output_tokens += response.output_tokens

        response_parts = split_ai_response(response.text)
        response_text = "\n\n".join(response_parts)
        base_message_id = outbound_message_id or uuid4()
        if side_effect_guard is not None:
            side_effect_guard()
        if handoff_reason is not None:
            self._conversations.update_mode(
                tenant_id,
                conversation_id,
                ConversationMode.HUMAN,
                None,
                commit=False,
            )
            self._events.publish(
                DomainEvent(
                    name="HumanHandoffRequested",
                    tenant_id=tenant_id,
                    payload={
                        "conversation_id": str(conversation_id),
                        "reason": handoff_reason,
                    },
                )
            )
        if send_to_channel:
            channel_credentials = self._credentials.get(tenant.slug)
            if channel_credentials is None:
                raise ConfigurationError(
                    "Canal de mensagens não configurado para esta empresa"
                )
        for index, part in enumerate(response_parts):
            message_id = base_message_id if index == 0 else uuid5(base_message_id, str(index))
            outbound = Message(
                id=message_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                direction=MessageDirection.OUTBOUND,
                author_type=MessageAuthor.AI,
                text=part,
                channel=conversation.channel,
            )
            if send_to_channel:
                sent = self._channel.send_message(
                    channel_credentials,
                    conversation.phone,
                    part,
                    idempotency_key=f"{base_message_id}:{index}",
                )
                outbound.external_message_id = sent.external_message_id
            self._conversations.record_outbound(tenant_id, outbound, commit=False)

        audit = self._audit_logs.create(
            AiAuditLog(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                input_text=user_text,
                detected_intent=response.detected_intent,
                tools_called=tools_called,
                chunks_used=chunks_used,
                response_text=response_text,
                model=response.model,
                tokens_used=total_tokens,
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                handoff_reason=handoff_reason,
                agent_key=agent_key,
            )
        )
        self._events.publish(
            DomainEvent(
                name="AiResponseGenerated",
                tenant_id=tenant_id,
                payload={
                    "conversation_id": str(conversation_id),
                    "audit_log_id": str(audit.id),
                },
            )
        )
        return AiAgentResult(
            response_text=response_text,
            detected_intent=response.detected_intent,
            tools_called=tools_called,
            chunks_used=chunks_used,
            model=response.model,
            tokens_used=total_tokens,
            handoff_reason=handoff_reason,
            response_parts=response_parts,
        )

    def _execute_tool(
        self, name: str, arguments: dict[str, Any], tenant_id: UUID, conversation_id: UUID
    ) -> dict[str, Any]:
        if name == "search_knowledge_base":
            query = str(arguments.get("query") or "")
            embedding = self._ai.get_embedding(query)
            results = self._knowledge.search_by_embedding(tenant_id, embedding, 5)
            return {"results": [result.content for result in results]}
        if name == "request_human_handoff":
            reason = str(arguments.get("reason") or "ai_requested")
            return {"status": "requested", "reason": reason}
        if name == "create_or_update_lead":
            if self._lead_qualification is None:
                return {"status": "unavailable"}
            lead = self._lead_qualification.create_or_update_lead(
                tenant_id,
                arguments,
                conversation_id=conversation_id,
                handoff_reason=_optional_text(arguments.get("handoff_reason")),
            )
            return {
                "status": "qualified",
                "lead_demand_id": str(lead.id),
                "crm_contact_id": lead.crm_contact_id,
                "crm_deal_id": lead.crm_deal_id,
            }
        if name == "search_properties":
            if self._properties is None:
                return {"status": "unavailable", "properties": []}
            properties = self._properties.search_by_filters(
                tenant_id,
                city=_optional_text(arguments.get("city")),
                purpose=_optional_text(arguments.get("purpose")),
                property_type=_optional_text(arguments.get("property_type")),
                neighborhoods=_string_list(arguments.get("neighborhoods")),
                price_min=_decimal(arguments.get("price_min")),
                price_max=_decimal(arguments.get("price_max")),
                bedrooms=_integer(arguments.get("bedrooms")),
                parking_spaces=_integer(arguments.get("parking_spaces")),
                internal_only=True,
                limit=5,
            )
            return {
                "status": "found" if properties else "not_found",
                "properties": [
                    {
                        "id": str(item.id),
                        "title": item.title,
                        "city": item.city,
                        "neighborhood": item.neighborhood,
                        "price": str(item.price) if item.price is not None else None,
                        "bedrooms": item.bedrooms,
                        "parking_spaces": item.parking_spaces,
                        "description": item.description,
                        "property_type": item.property_type,
                        "purpose": item.purpose.value if item.purpose else None,
                        "area": item.area,
                    }
                    for item in properties
                ],
            }
        if name == "record_usage":
            return {"status": "recorded"}
        return {"status": "unsupported_tool"}

    def _handoff_for_restricted_intent(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        user_text: str,
        reason: str,
        *,
        send_to_channel: bool,
        tenant_slug: str,
        phone: str,
        channel: Any,
        outbound_message_id: UUID | None,
        side_effect_guard: Callable[[], None] | None,
    ) -> AiAgentResult:
        text = (
            "Esse assunto precisa ser tratado por um atendente humano. "
            "Vou encaminhar sua solicitação para a equipe responsável."
        )
        if side_effect_guard is not None:
            side_effect_guard()
        self._events.publish(
            DomainEvent(
                name="HumanHandoffRequested",
                tenant_id=tenant_id,
                payload={"conversation_id": str(conversation_id), "reason": reason},
            )
        )
        self._conversations.update_mode(
            tenant_id,
            conversation_id,
            ConversationMode.HUMAN,
            None,
            commit=False,
        )
        outbound = Message(
            id=outbound_message_id or uuid4(),
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            direction=MessageDirection.OUTBOUND,
            author_type=MessageAuthor.AI,
            text=text,
            channel=channel,
        )
        if send_to_channel:
            channel_credentials = self._credentials.get(tenant_slug)
            if channel_credentials is None:
                raise ConfigurationError(
                    "Canal de mensagens não configurado para esta empresa"
                )
            sent = self._channel.send_message(channel_credentials, phone, text)
            outbound.external_message_id = sent.external_message_id
        self._conversations.record_outbound(tenant_id, outbound, commit=False)
        audit = self._audit_logs.create(
            AiAuditLog(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                input_text=user_text,
                detected_intent="escalada_humano",
                tools_called=[{"name": "request_human_handoff", "arguments": {"reason": reason}}],
                chunks_used=[],
                response_text=text,
                model="guardrail",
                tokens_used=0,
                handoff_reason=reason,
                agent_key="leads",
            )
        )
        self._events.publish(
            DomainEvent(
                name="AiResponseGenerated",
                tenant_id=tenant_id,
                payload={
                    "conversation_id": str(conversation_id),
                    "audit_log_id": str(audit.id),
                },
            )
        )
        return AiAgentResult(
            response_text=text,
            detected_intent="escalada_humano",
            tools_called=[{"name": "request_human_handoff", "arguments": {"reason": reason}}],
            chunks_used=[],
            model="guardrail",
            tokens_used=0,
            handoff_reason=reason,
        )

    @staticmethod
    def _messages_from_history(messages: list[Message]) -> list[dict[str, str]]:
        converted: list[dict[str, str]] = []
        for message in messages:
            if message.author_type is MessageAuthor.CUSTOMER:
                role = "user"
                prefix = ""
            elif message.author_type is MessageAuthor.HUMAN:
                role = "assistant"
                prefix = "[Mensagem anterior da equipe humana] "
            elif message.author_type is MessageAuthor.SYSTEM:
                role = "assistant"
                prefix = "[Contexto interno] "
            else:
                role = "assistant"
                prefix = ""
            media_context = "\n".join(
                str(attachment.get("ai_text") or "").strip()
                for attachment in message.attachments
                if str(attachment.get("ai_text") or "").strip()
            )
            content = "\n".join(part for part in (message.text.strip(), media_context) if part)
            if content:
                converted.append({"role": role, "content": f"{prefix}{content}"})
        return converted

    def _conversation_context(
        self, tenant_id: UUID, conversation: Any
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "customer_name": conversation.customer_name,
            "phone": conversation.phone,
            "channel": conversation.channel.value,
            "current_intent": conversation.current_intent,
        }
        if self._lead_demands is not None:
            demand = self._lead_demands.get_open_by_phone(tenant_id, conversation.phone)
            if demand is not None:
                context["known_demand"] = {
                    "lead_name": demand.lead_name,
                    "purpose": demand.purpose.value if demand.purpose else None,
                    "property_type": demand.property_type,
                    "city": demand.city,
                    "neighborhoods": demand.neighborhoods,
                    "price_min": str(demand.price_min) if demand.price_min is not None else None,
                    "price_max": str(demand.price_max) if demand.price_max is not None else None,
                    "bedrooms": demand.bedrooms,
                    "parking_spaces": demand.parking_spaces,
                    "min_area": demand.min_area,
                    "notes": demand.notes,
                    "status": demand.status.value,
                }
        return context

    @staticmethod
    def _resolve_agent(settings: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        agents = settings.get("agents") if isinstance(settings, dict) else None
        if not isinstance(agents, dict):
            return "leads", _effective_agent_settings({})
        configured = agents.get("leads")
        return "leads", _effective_agent_settings(
            configured if isinstance(configured, dict) else {}
        )

    @staticmethod
    def _system_prompt(
        settings: dict[str, Any],
        agent_key: str,
        agent_settings: dict[str, Any],
        chunks: list[Any],
        conversation_context: dict[str, Any] | None = None,
    ) -> str:
        profile = settings.get("profile", {}) if isinstance(settings, dict) else {}
        prompt_profile = {
            key: profile[key]
            for key in ("display_name", "legal_name", "regions")
            if isinstance(profile, dict) and profile.get(key) not in (None, "")
        }
        legacy_hours = profile.get("business_hours") if isinstance(profile, dict) else None
        prompt_profile["horario_de_atendimento"] = _business_hours_text(legacy_hours)
        structured_profile = json.dumps(prompt_profile, ensure_ascii=False, default=str)
        structured_agent = json.dumps(
            {
                "publico_atendido": "Leads e clientes",
                "canais_ativos": _active_agent_channels(settings),
                **agent_settings,
            },
            ensure_ascii=False,
            default=str,
        )
        structured_context = json.dumps(
            conversation_context or {}, ensure_ascii=False, default=str
        )
        rag = "\n\n".join(chunk.content for chunk in chunks)
        return (
            f"Você é o agente de qualificação de leads do ImobIA (agente: {agent_key}). "
            "Atenda novos interessados de forma natural, breve e prestativa. Colete aos poucos "
            "nome, telefone, finalidade de compra ou locação, cidade, bairros, tipo de imóvel, "
            "faixa de valor, quartos, vagas e urgência. Não repita perguntas já respondidas. "
            "Quando houver critérios suficientes, salve a demanda com create_or_update_lead e "
            "busque imóveis com search_properties. Essa ferramenta contém somente a carteira "
            "própria autorizada para oferta. Nunca mencione portal, captação, anunciante ou URL "
            "de origem. Nunca invente imóveis ou dados ausentes. "
            "Se não houver resultado, explique isso e informe que a equipe poderá iniciar uma "
            "busca externa. Não negocie valores, não dê orientação jurídica conclusiva e peça "
            "handoff quando a autonomia for insuficiente ou o lead pedir uma pessoa. "
            "Respeite integralmente handoff_rules e restrictions da configuração. Ao transferir, "
            "use a transfer_message configurada, adaptando apenas o mínimo necessário ao contexto. "
            "Faça uma pergunta por vez. Escreva como uma conversa de WhatsApp: frases curtas, "
            "linguagem simples e sem tabelas ou títulos. Obedeça ao tom de voz e à quantidade "
            "de emojis definidos na configuração do agente. 'none' significa nenhum emoji, "
            "'low' significa no máximo um ocasionalmente e 'moderate' permite até dois quando "
            "forem naturais. "
            "Não repita o nome do cliente nem comece respostas seguidas com a mesma expressão. "
            "Entenda confirmações curtas como 'sim', 'pode ser' e 'bora' pelo contexto anterior. "
            "Evite jargão, ponto e vírgula e travessão. Não afirme que uma ação foi concluída sem "
            "o retorno bem-sucedido da ferramenta correspondente. Use transcrições e descrições "
            "de mídia apenas como contexto auxiliar, sem transformar inferências visuais em "
            "fatos.\n\n"
            f"Perfil da empresa:\n{structured_profile}\n\n"
            f"Configuração deste agente:\n{structured_agent}\n\n"
            f"Contexto cadastral já confirmado:\n{structured_context}\n\n"
            f"Base de conhecimento recuperada:\n{rag}"
        )

    @staticmethod
    def _tool_definitions(agent_key: str = "leads") -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "search_knowledge_base",
                "description": "Busca trechos da base de conhecimento do tenant atual.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "request_human_handoff",
                "description": (
                    "Solicita atendimento humano quando houver baixa confiança ou regra restritiva."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"reason": {"type": "string"}},
                    "required": ["reason"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "record_usage",
                "description": "Registra um uso de IA no módulo atual.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "module": {"type": "string"},
                    },
                    "required": ["type", "module"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "create_or_update_lead",
                "description": (
                    "Cria ou atualiza a demanda quando os critérios essenciais estiverem claros."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_name": {"type": ["string", "null"]},
                        "phone": {"type": "string"},
                        "email": {"type": ["string", "null"]},
                        "purpose": {"type": ["string", "null"], "enum": ["buy", "rent", None]},
                        "property_type": {"type": ["string", "null"]},
                        "city": {"type": ["string", "null"]},
                        "neighborhoods": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "price_min": {"type": ["number", "null"]},
                        "price_max": {"type": ["number", "null"]},
                        "bedrooms": {"type": ["integer", "null"]},
                        "parking_spaces": {"type": ["integer", "null"]},
                        "min_area": {"type": ["integer", "null"]},
                        "notes": {"type": ["string", "null"]},
                        "handoff_reason": {"type": ["string", "null"]},
                    },
                    "required": [
                        "lead_name",
                        "phone",
                        "email",
                        "purpose",
                        "property_type",
                        "city",
                        "neighborhoods",
                        "price_min",
                        "price_max",
                        "bedrooms",
                        "parking_spaces",
                        "min_area",
                        "notes",
                        "handoff_reason",
                    ],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "search_properties",
                "description": "Busca imóveis reais do tenant compatíveis com a demanda do lead.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": ["string", "null"]},
                        "purpose": {
                            "type": ["string", "null"],
                            "enum": ["buy", "rent", None],
                        },
                        "property_type": {"type": ["string", "null"]},
                        "neighborhoods": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "price_min": {"type": ["number", "null"]},
                        "price_max": {"type": ["number", "null"]},
                        "bedrooms": {"type": ["integer", "null"]},
                        "parking_spaces": {"type": ["integer", "null"]},
                    },
                    "required": [
                        "city",
                        "purpose",
                        "property_type",
                        "neighborhoods",
                        "price_min",
                        "price_max",
                        "bedrooms",
                        "parking_spaces",
                    ],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]


def split_ai_response(text: str, *, max_parts: int = 5, target_chars: int = 500) -> list[str]:
    cleaned = str(text or "").strip().replace("**", "")
    cleaned = re.sub(r"\s*;\s*", ". ", cleaned)
    cleaned = re.sub(r"\s+[—–]\s+", ", ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    if not cleaned:
        return ["Desculpe, não consegui preparar uma resposta agora. Pode repetir sua mensagem?"]

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", cleaned) if part.strip()]
    parts: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= target_chars:
            parts.append(paragraph)
            continue
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            if sentence.strip()
        ]
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > target_chars:
                parts.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            parts.append(current)

    if len(parts) > max_parts:
        parts = [*parts[: max_parts - 1], "\n\n".join(parts[max_parts - 1 :])]
    return parts or [cleaned]


def _business_hours_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip() or "Não informado"
    if not isinstance(value, dict):
        return "Não informado"
    days = value.get("days")
    if not isinstance(days, dict):
        return "Não informado"
    labels = {
        "monday": "segunda-feira",
        "tuesday": "terça-feira",
        "wednesday": "quarta-feira",
        "thursday": "quinta-feira",
        "friday": "sexta-feira",
        "saturday": "sábado",
        "sunday": "domingo",
    }
    descriptions: list[str] = []
    for key, label in labels.items():
        schedule = days.get(key)
        if not isinstance(schedule, dict) or not schedule.get("enabled"):
            descriptions.append(f"{label}: fechado")
            continue
        start = str(schedule.get("start") or "horário não informado")
        end = str(schedule.get("end") or "horário não informado")
        description = f"{label}: das {start} às {end}"
        if schedule.get("break_enabled"):
            break_start = str(schedule.get("break_start") or "?")
            break_end = str(schedule.get("break_end") or "?")
            description += f", com intervalo das {break_start} às {break_end}"
        descriptions.append(description)
    timezone = str(value.get("timezone") or "America/Sao_Paulo")
    return "; ".join(descriptions) + f". Fuso horário: {timezone}."


def _effective_agent_settings(configured: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "name": "Agente de Leads",
        "status": "active",
        "handoff_rules": (
            "Lead pronto para visita, pedido de negociação, dúvida complexa ou baixa "
            "confiança da IA."
        ),
        "restrictions": (
            "Não prometer disponibilidade, não negociar valores finais e não assumir "
            "compromisso em nome do corretor."
        ),
        "transfer_message": (
            "Vou acionar um corretor da equipe para seguir com as melhores opções."
        ),
        "voice_tone": "friendly",
        "emoji_usage": "low",
    }
    return {
        key: configured.get(key, default)
        for key, default in defaults.items()
    }


def _active_agent_channels(settings: dict[str, Any]) -> list[str]:
    channels = settings.get("channels") if isinstance(settings, dict) else None
    if not isinstance(channels, dict):
        return []
    active: list[str] = []
    for name, configuration in channels.items():
        if not isinstance(configuration, dict):
            continue
        status = str(configuration.get("status") or "pending").lower()
        configured_agents = configuration.get("agents")
        has_lead_agent = (
            isinstance(configured_agents, list) and "leads" in configured_agents
        ) or (configured_agents is None and configuration.get("agent", "leads") == "leads")
        if status == "connected" and has_lead_agent:
            active.append(str(name))
    return active


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
