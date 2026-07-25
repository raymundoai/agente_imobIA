import {
  Building2,
  ClipboardList,
  Clock,
  FileUp,
  Image,
  MessageSquare,
  Mic,
  Paperclip,
  Phone,
  Plus,
  Search,
  Send,
  UserCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { request } from "../api/client";
import type { Conversation, ConversationDetail, LeadDemand, Message, Property } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { DemandModal } from "../components/DemandModal";
import { formatCurrency, labelOrDash } from "../lib/format";
import { getLocalProperties } from "../lib/localProperties";

type ContactType = "all" | "lead" | "active_customer";
type CustomerRole = "all" | "owner" | "tenant";
type ConversationMeta = {
  contact_type: "lead" | "active_customer";
  customer_role: "buyer" | "tenant" | "owner" | "unknown";
};
type ConversationWithMeta = Conversation & Partial<ConversationMeta>;
type ChatMessage = Message & { sharedProperty?: Property };

export function ConversationsPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<ConversationWithMeta[]>([]);
  const [selectedId, setSelectedId] = useState<string>(demoConversations[0].id);
  const [query, setQuery] = useState("");
  const [contactFilter, setContactFilter] = useState<ContactType>("all");
  const [roleFilter, setRoleFilter] = useState<CustomerRole>("all");
  const [draft, setDraft] = useState("");
  const [recording, setRecording] = useState(false);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [propertyShareOpen, setPropertyShareOpen] = useState(false);
  const [demandModalOpen, setDemandModalOpen] = useState(false);
  const [properties, setProperties] = useState<Property[]>([]);
  const [aiEnabledById, setAiEnabledById] = useState<Record<string, boolean>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [messagesById, setMessagesById] = useState<Record<string, ChatMessage[]>>(() =>
    Object.fromEntries(
      Object.entries(demoConversationDetails).map(([id, detail]) => [id, detail.messages]),
    ),
  );
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void request<Conversation[]>("/conversations", {}, token)
      .then((conversations) => {
        const nextItems = conversations.length ? conversations.map(withDefaultMeta) : demoConversations;
        setItems(nextItems);
        setSelectedId((current) => nextItems.some((item) => item.id === current) ? current : nextItems[0].id);
      })
      .catch(() => setItems(demoConversations));
  }, [token]);

  useEffect(() => {
    void request<Property[]>("/properties", {}, token)
      .then((apiProperties) => setProperties([...getLocalProperties(), ...apiProperties]))
      .catch(() => setProperties(getLocalProperties()));
  }, [token]);

  useEffect(() => {
    if (!selectedId || selectedId.startsWith("demo-")) {
      return;
    }
    void request<ConversationDetail>(`/conversations/${selectedId}`, {}, token)
      .then((detail) => {
        setMessagesById((current) => ({ ...current, [selectedId]: detail.messages }));
        setItems((current) =>
          current.map((item) => (item.id === selectedId ? { ...item, ...detail } : item)),
        );
      })
      .catch((error) => setActionError(readActionError(error)));
  }, [selectedId, token]);

  const visibleItems = useMemo(() => {
    const source = items.length ? items : demoConversations;
    const normalized = query.trim().toLowerCase();
    return source.filter((item) => {
      const meta = getConversationMeta(item);
      const matchesContact =
        contactFilter === "all" || meta.contact_type === contactFilter;
      const matchesRole =
        roleFilter === "all" ||
        (meta.contact_type === "active_customer" && meta.customer_role === roleFilter);
      const matchesSearch =
        !normalized ||
        [
          item.customer_name,
          item.phone,
          item.status,
          item.mode,
          contactTypeLabels[meta.contact_type],
          roleLabels[meta.customer_role],
        ].some((value) => String(value ?? "").toLowerCase().includes(normalized));
      return matchesContact && matchesRole && matchesSearch;
    });
  }, [contactFilter, items, query, roleFilter]);

  const selected = visibleItems.find((item) => item.id === selectedId) ?? visibleItems[0];
  const selectedMeta = selected ? getConversationMeta(selected) : null;
  const demoDetail = demoConversationDetails[selected?.id ?? demoConversations[0].id];
  const selectedMessages = selected ? messagesById[selected.id] ?? demoDetail?.messages ?? [] : [];
  const aiEnabled = selected
    ? aiEnabledById[selected.id] ?? selected.mode !== "human"
    : true;
  const agentName = getAgentName(selectedMeta);

  async function toggleAi() {
    if (!selected) {
      return;
    }
    if (selected.id.startsWith("demo-")) {
      setAiEnabledById((current) => ({ ...current, [selected.id]: !aiEnabled }));
      return;
    }
    setActionError(null);
    try {
      const updated = await request<Conversation>(
        `/conversations/${selected.id}/mode`,
        { method: "PATCH", body: JSON.stringify({ mode: aiEnabled ? "human" : "ai" }) },
        token,
      );
      setItems((current) =>
        current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
      );
      setAiEnabledById((current) => ({ ...current, [selected.id]: updated.mode !== "human" }));
    } catch (error) {
      setActionError(readActionError(error));
    }
  }

  async function assumeConversation() {
    if (!selected) {
      return;
    }
    if (!selected.id.startsWith("demo-")) {
      setActionError(null);
      try {
        const updated = await request<Conversation>(
          `/conversations/${selected.id}/mode`,
          { method: "PATCH", body: JSON.stringify({ mode: "human" }) },
          token,
        );
        setItems((current) =>
          current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
        );
      } catch (error) {
        setActionError(readActionError(error));
        return;
      }
    }
    setAiEnabledById((current) => ({ ...current, [selected.id]: false }));
    appendMessage(selected.id, {
      direction: "outbound",
      author_type: "system",
      text: "Conversa assumida pela equipe. A IA foi pausada para este atendimento.",
    });
  }

  async function sendMessage() {
    if (!selected || !draft.trim()) {
      return;
    }
    const text = draft.trim();
    if (!selected.id.startsWith("demo-")) {
      setActionError(null);
      try {
        if (selected.mode !== "human") {
          await request(
            `/conversations/${selected.id}/mode`,
            { method: "PATCH", body: JSON.stringify({ mode: "human" }) },
            token,
          );
        }
        const created = await request<Message>(
          `/conversations/${selected.id}/messages`,
          { method: "POST", body: JSON.stringify({ text }) },
          token,
        );
        setMessagesById((current) => ({
          ...current,
          [selected.id]: [...(current[selected.id] ?? []), created],
        }));
        setItems((current) =>
          current.map((item) =>
            item.id === selected.id
              ? { ...item, mode: "human", status: "waiting_human" }
              : item,
          ),
        );
      } catch (error) {
        setActionError(readActionError(error));
        return;
      }
    } else {
      appendMessage(selected.id, {
        direction: "outbound",
        author_type: "human",
        text,
      });
    }
    setAiEnabledById((current) => ({ ...current, [selected.id]: false }));
    setDraft("");
  }

  function shareProperty(property: Property) {
    if (!selected) {
      return;
    }

    appendMessage(selected.id, {
      direction: "outbound",
      author_type: "human",
      text: buildPropertyShareText(property),
      sharedProperty: property,
    });
    setAiEnabledById((current) => ({ ...current, [selected.id]: false }));
    setPropertyShareOpen(false);
  }

  function attach(kind: "arquivo" | "imagem", files: FileList | null) {
    if (!selected || !files?.[0]) {
      return;
    }
    appendMessage(selected.id, {
      direction: "outbound",
      author_type: "human",
      text: `${kind === "imagem" ? "Imagem" : "Arquivo"} anexado: ${files[0].name}`,
    });
    setAiEnabledById((current) => ({ ...current, [selected.id]: false }));
  }

  function handleDemandCreated(demand: LeadDemand) {
    if (!selected) {
      return;
    }
    setAiEnabledById((current) => ({ ...current, [selected.id]: false }));
    appendMessage(selected.id, {
      direction: "outbound",
      author_type: "system",
      text: `Demanda cadastrada e busca iniciada para ${demand.property_type ?? "imóvel"} em ${demand.city ?? "cidade a definir"}.`,
    });
  }

  function registerCustomerRequest() {
    if (!selected || !selectedMeta) {
      return;
    }
    setAiEnabledById((current) => ({ ...current, [selected.id]: false }));
    appendMessage(selected.id, {
      direction: "outbound",
      author_type: "system",
      text:
        selectedMeta.customer_role === "tenant"
          ? "Chamado aberto para acompanhar esta solicitação do inquilino."
          : "Solicitação do proprietário registrada para acompanhamento da equipe.",
    });
  }

  function appendMessage(
    conversationId: string,
    message: Pick<Message, "direction" | "author_type" | "text"> & { sharedProperty?: Property },
  ) {
    setMessagesById((current) => ({
      ...current,
      [conversationId]: [
        ...(current[conversationId] ?? demoConversationDetails[conversationId]?.messages ?? []),
        {
          id: `${conversationId}-${Date.now()}`,
          created_at: new Date().toISOString(),
          ...message,
        },
      ],
    }));
  }

  return (
    <section className="page-stack chat-page">
      <div className="inbox-layout">
        <aside className="inbox-list">
          <div className="conversation-filters">
            {contactFilters.map((filter) => (
              <button
                className={contactFilter === filter.key ? "filter-chip active" : "filter-chip"}
                key={filter.key}
                onClick={() => {
                  setContactFilter(filter.key);
                  if (filter.key !== "active_customer") {
                    setRoleFilter("all");
                  }
                }}
                type="button"
              >
                {filter.label}
              </button>
            ))}
          </div>
          {contactFilter === "active_customer" ? (
            <div className="conversation-filters secondary">
              {roleFilters.map((filter) => (
                <button
                  className={roleFilter === filter.key ? "filter-chip active" : "filter-chip"}
                  key={filter.key}
                  onClick={() => setRoleFilter(filter.key)}
                  type="button"
                >
                  {filter.label}
                </button>
              ))}
            </div>
          ) : null}
          <label className="inbox-search">
            <Search size={16} />
            <input
              aria-label="Buscar conversas"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar por cliente, telefone ou status"
              value={query}
            />
          </label>
          <div className="conversation-list">
            {visibleItems.map((item) => {
              const isActive = item.id === selected?.id;
              const itemAiEnabled = aiEnabledById[item.id] ?? item.mode !== "human";
              return (
                <button
                  className={isActive ? "conversation-item active" : "conversation-item"}
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                  type="button"
                >
                  <span className="conversation-avatar">
                    <MessageSquare size={16} />
                  </span>
                  <span>
                    <strong>{item.customer_name ?? item.phone}</strong>
                    <small>{item.phone}</small>
                    <small>
                      {contactTypeLabels[getConversationMeta(item).contact_type]} ·{" "}
                      {roleLabels[getConversationMeta(item).customer_role]}
                    </small>
                  </span>
                  <Badge variant={itemAiEnabled ? "success" : "accent"}>
                    {itemAiEnabled ? "IA" : "Equipe"}
                  </Badge>
                </button>
              );
            })}
          </div>
        </aside>

        <article className="chat-panel">
          <div className="chat-panel-header">
            <div>
              <h2>{selected?.customer_name ?? selected?.phone ?? "Conversa"}</h2>
              <p>
                <Phone size={14} />
                {selected?.phone ?? "Sem telefone"}
                <span>·</span>
                {selected?.channel === "telegram" ? "Telegram" : "WhatsApp"}
                <Clock size={14} />
                {selected?.status === "waiting_human" ? "Aguardando equipe" : "Em atendimento"}
                {selectedMeta ? (
                  <>
                    <span>·</span>
                    {contactTypeLabels[selectedMeta.contact_type]}
                    <span>·</span>
                    {roleLabels[selectedMeta.customer_role]}
                  </>
                ) : null}
              </p>
            </div>
            <div className="toolbar-actions">
              <button
                className="button-outline"
                onClick={() => void assumeConversation()}
                type="button"
              >
                <UserCheck size={15} />
                Assumir
              </button>
              {selectedMeta?.contact_type === "active_customer" ? (
                <button className="button-outline" onClick={registerCustomerRequest} type="button">
                  <ClipboardList size={15} />
                  {selectedMeta.customer_role === "tenant" ? "Abrir chamado" : "Registrar solicitação"}
                </button>
              ) : (
                <button
                  className="button-outline"
                  onClick={() => setDemandModalOpen(true)}
                  type="button"
                >
                  <Plus size={15} />
                  Cadastrar demanda
                </button>
              )}
            </div>
          </div>

          <div className="chat-controls">
            <button
              aria-pressed={aiEnabled}
              className={aiEnabled ? "ai-toggle active" : "ai-toggle"}
              aria-label={aiEnabled ? "Desativar agente" : "Ativar agente"}
              onClick={() => void toggleAi()}
              type="button"
            >
              <span />
            </button>
            <p className="agent-status">
              <strong>{agentName}</strong> está {aiEnabled ? "ativo" : "desativado"} nessa conversa.
            </p>
          </div>
          {actionError ? <div className="error-box">{actionError}</div> : null}

          <div className="chat-list embedded">
            {selectedMessages.map((message) => (
              <article className={`message ${message.direction}`} key={message.id}>
                <small>{authorLabels[message.author_type] ?? message.author_type}</small>
                <p>{message.text}</p>
                {message.sharedProperty ? <SharedPropertyPreview property={message.sharedProperty} /> : null}
              </article>
            ))}
          </div>

          <div className="chat-context">
            <div>
              <span>Interesse</span>
              <strong>{demoDetail?.current_intent ?? "Qualificação de lead"}</strong>
            </div>
          </div>

          <div className="chat-composer">
            <input
              accept="image/*"
              hidden
              onChange={(event) => {
                attach("imagem", event.target.files);
                setAttachmentMenuOpen(false);
                event.target.value = "";
              }}
              ref={imageInputRef}
              type="file"
            />
            <input
              hidden
              onChange={(event) => {
                attach("arquivo", event.target.files);
                setAttachmentMenuOpen(false);
                event.target.value = "";
              }}
              ref={fileInputRef}
              type="file"
            />
            <div className="composer-tools">
              <div className="attachment-picker">
                <button
                  aria-expanded={attachmentMenuOpen}
                  aria-label="Anexar"
                  className="icon-button"
                  onClick={() => setAttachmentMenuOpen((current) => !current)}
                  title="Anexar"
                  type="button"
                >
                  <Paperclip size={17} />
                </button>
                {attachmentMenuOpen ? (
                  <div className="attachment-popover">
                    <button onClick={() => fileInputRef.current?.click()} type="button">
                      <FileUp size={16} />
                      Documento
                    </button>
                    <button onClick={() => imageInputRef.current?.click()} type="button">
                      <Image size={16} />
                      Imagem
                    </button>
                  </div>
                ) : null}
              </div>
              <button
                aria-label="Compartilhar imóvel"
                className="icon-button"
                onClick={() => setPropertyShareOpen(true)}
                title="Compartilhar imóvel"
                type="button"
              >
                <Building2 size={17} />
              </button>
              <button
                aria-label={recording ? "Parar áudio" : "Enviar áudio"}
                className={recording ? "icon-button recording" : "icon-button"}
                onClick={() => setRecording((current) => !current)}
                title={recording ? "Parar áudio" : "Enviar áudio"}
                type="button"
              >
                <Mic size={17} />
              </button>
            </div>
            <textarea
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder={aiEnabled ? "Digite para assumir e responder..." : "Responder como equipe..."}
              value={draft}
            />
            <button
              className="send-button"
              disabled={!draft.trim()}
              onClick={() => void sendMessage()}
              type="button"
            >
              <Send size={17} />
              Enviar
            </button>
          </div>
        </article>
      </div>
      <DemandModal
        initialLeadName={selected?.customer_name}
        initialPhone={selected?.phone}
        isOpen={demandModalOpen}
        onClose={() => setDemandModalOpen(false)}
        onCreated={handleDemandCreated}
      />
      {propertyShareOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section aria-modal="true" className="demand-modal property-share-modal" role="dialog">
            <div className="modal-header">
              <div>
                <h2>Compartilhar imóvel</h2>
                <p>Selecione um imóvel para enviar fotos e descrição para o lead.</p>
              </div>
              <button className="icon-button" onClick={() => setPropertyShareOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            {properties.length > 0 ? (
              <div className="property-share-list">
                {properties.map((property) => (
                  <article className="property-share-item" key={property.id}>
                    <PropertyShareThumb property={property} />
                    <div>
                      <strong>{property.title}</strong>
                      <span>
                        {property.neighborhood ? `${property.neighborhood}, ` : ""}
                        {property.city}
                      </span>
                      <small>
                        {formatCurrency(property.price)} · {labelOrDash(property.property_type)} ·{" "}
                        {labelOrDash(property.purpose)}
                      </small>
                    </div>
                    <button onClick={() => shareProperty(property)} type="button">
                      Enviar
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                Nenhum imóvel cadastrado para compartilhar.
              </div>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}

function SharedPropertyPreview({ property }: { property: Property }) {
  const imageUrls = getPropertyImageUrls(property);

  return (
    <div className="shared-property-preview">
      {imageUrls.length > 0 ? (
        <div className="shared-property-images">
          {imageUrls.slice(0, 3).map((url, index) => (
            <img alt={`${property.title} - foto ${index + 1}`} key={url} src={url} />
          ))}
        </div>
      ) : null}
      <div>
        <strong>{property.title}</strong>
        <span>
          {formatCurrency(property.price)} · {labelOrDash(property.property_type)}
        </span>
      </div>
    </div>
  );
}

function PropertyShareThumb({ property }: { property: Property }) {
  const imageUrl = getPropertyImageUrls(property)[0];

  return (
    <div className="property-share-thumb">
      {imageUrl ? <img alt={property.title} src={imageUrl} /> : <Building2 size={20} />}
    </div>
  );
}

function getPropertyImageUrls(property: Property) {
  return property.images
    .map((image) => image.url)
    .filter((url): url is string => typeof url === "string" && Boolean(url.trim()));
}

function buildPropertyShareText(property: Property) {
  const location = [property.neighborhood, property.city].filter(Boolean).join(", ");
  const details = [
    formatCurrency(property.price),
    labelOrDash(property.property_type),
    property.bedrooms ? `${property.bedrooms} quarto${property.bedrooms > 1 ? "s" : ""}` : null,
    property.parking_spaces ? `${property.parking_spaces} vaga${property.parking_spaces > 1 ? "s" : ""}` : null,
    property.area ? `${property.area} m²` : null,
  ].filter(Boolean);

  return `Estou te enviando uma opção de imóvel: ${property.title}${location ? ` em ${location}` : ""}. ${details.join(" · ")}.`;
}

function readActionError(error: unknown) {
  return error instanceof Error ? error.message : "Não foi possível concluir a ação.";
}

export const demoConversations: ConversationWithMeta[] = [
  {
    id: "demo-conversation-1",
    phone: "+55 51 99988-1122",
    customer_name: "Marina Costa",
    status: "open",
    mode: "ai",
    last_message_at: new Date().toISOString(),
    contact_type: "lead",
    customer_role: "buyer",
  },
  {
    id: "demo-conversation-2",
    phone: "+55 51 98877-3344",
    customer_name: "Rafael Almeida",
    status: "waiting_human",
    mode: "human",
    last_message_at: new Date().toISOString(),
    contact_type: "active_customer",
    customer_role: "tenant",
  },
  {
    id: "demo-conversation-3",
    phone: "+55 51 97766-5500",
    customer_name: "Patricia Lima",
    status: "open",
    mode: "ai",
    last_message_at: new Date().toISOString(),
    contact_type: "active_customer",
    customer_role: "owner",
  },
];

export const demoConversationDetails: Record<string, ConversationDetail & { current_intent?: string }> = {
  "demo-conversation-1": {
    ...demoConversations[0],
    current_intent: "Compra de apartamento",
    messages: [
      {
        id: "m1",
        direction: "inbound",
        author_type: "customer",
        text: "Oi, procuro apartamento de 2 quartos em Novo Hamburgo, até R$ 420 mil.",
        created_at: new Date().toISOString(),
      },
      {
        id: "m2",
        direction: "outbound",
        author_type: "ai",
        text: "Perfeito. Você prefere algum bairro específico e precisa de vaga de garagem?",
        created_at: new Date().toISOString(),
      },
      {
        id: "m3",
        direction: "inbound",
        author_type: "customer",
        text: "Idealmente Centro ou Hamburgo Velho. Uma vaga já resolve.",
        created_at: new Date().toISOString(),
      },
    ],
  },
  "demo-conversation-2": {
    ...demoConversations[1],
    current_intent: "Manutenção no imóvel",
    messages: [
      {
        id: "m4",
        direction: "inbound",
        author_type: "customer",
        text: "Bom dia, sou inquilino do apê 304. O chuveiro parou de aquecer desde ontem.",
        created_at: new Date().toISOString(),
      },
      {
        id: "m5",
        direction: "outbound",
        author_type: "ai",
        text: "Entendi. Você consegue enviar uma foto do disjuntor e informar se há cheiro de queimado?",
        created_at: new Date().toISOString(),
      },
    ],
  },
  "demo-conversation-3": {
    ...demoConversations[2],
    current_intent: "Repasse ao proprietário",
    messages: [
      {
        id: "m6",
        direction: "inbound",
        author_type: "customer",
        text: "Olá, gostaria de confirmar quando será feito o repasse do aluguel deste mês.",
        created_at: new Date().toISOString(),
      },
      {
        id: "m7",
        direction: "outbound",
        author_type: "ai",
        text: "Vou verificar com a equipe responsável e registrar sua solicitação para retorno.",
        created_at: new Date().toISOString(),
      },
    ],
  },
};

const authorLabels: Record<string, string> = {
  ai: "IA",
  customer: "Cliente",
  human: "Equipe",
  system: "Sistema",
};

const contactFilters: Array<{ key: ContactType; label: string }> = [
  { key: "all", label: "Todos" },
  { key: "lead", label: "Leads" },
  { key: "active_customer", label: "Clientes ativos" },
];

const roleFilters: Array<{ key: CustomerRole; label: string }> = [
  { key: "all", label: "Todos" },
  { key: "owner", label: "Proprietários" },
  { key: "tenant", label: "Inquilinos" },
];

const contactTypeLabels: Record<ConversationMeta["contact_type"], string> = {
  lead: "Lead",
  active_customer: "Cliente ativo",
};

const roleLabels: Record<ConversationMeta["customer_role"], string> = {
  buyer: "Comprador",
  tenant: "Inquilino",
  owner: "Proprietário",
  unknown: "Não identificado",
};

function withDefaultMeta(conversation: Conversation): ConversationWithMeta {
  return {
    ...conversation,
    contact_type: "lead",
    customer_role: "buyer",
  };
}

function getConversationMeta(conversation: ConversationWithMeta): ConversationMeta {
  return {
    contact_type: conversation.contact_type ?? "lead",
    customer_role: conversation.customer_role ?? "buyer",
  };
}

function getAgentName(meta: ConversationMeta | null) {
  if (meta?.contact_type === "active_customer") {
    return "Agente de Atendimento";
  }
  return "Agente de Leads";
}
