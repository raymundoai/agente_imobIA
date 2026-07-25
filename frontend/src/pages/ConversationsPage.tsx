import {
  Building2,
  Clock,
  MessageSquare,
  Phone,
  Plus,
  Search,
  Send,
  UserCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "../api/client";
import type { Conversation, ConversationDetail, LeadDemand, Message, Property } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { DemandModal } from "../components/DemandModal";
import { formatCurrency, labelOrDash } from "../lib/format";

type ChatMessage = Message & { sharedProperty?: Property };

export function ConversationsPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [propertyShareOpen, setPropertyShareOpen] = useState(false);
  const [demandModalOpen, setDemandModalOpen] = useState(false);
  const [properties, setProperties] = useState<Property[]>([]);
  const [aiEnabledById, setAiEnabledById] = useState<Record<string, boolean>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [messagesById, setMessagesById] = useState<Record<string, ChatMessage[]>>({});

  useEffect(() => {
    void request<Conversation[]>("/conversations", {}, token)
      .then((conversations) => {
        const nextItems = conversations;
        setItems(nextItems);
        setSelectedId((current) =>
          nextItems.some((item) => item.id === current) ? current : (nextItems[0]?.id ?? ""),
        );
      })
      .catch((error) => {
        setItems([]);
        setActionError(readActionError(error));
      });
  }, [token]);

  useEffect(() => {
    void request<Property[]>("/properties", {}, token)
      .then(setProperties)
      .catch((error) => {
        setProperties([]);
        setActionError(readActionError(error));
      });
  }, [token]);

  useEffect(() => {
    if (!selectedId) {
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
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      const matchesSearch =
        !normalized ||
        [
          item.customer_name,
          item.phone,
          item.status,
          item.mode,
        ].some((value) => String(value ?? "").toLowerCase().includes(normalized));
      return matchesSearch;
    });
  }, [items, query]);

  const selected = visibleItems.find((item) => item.id === selectedId) ?? visibleItems[0];
  const selectedMessages = selected ? messagesById[selected.id] ?? [] : [];
  const aiEnabled = selected
    ? aiEnabledById[selected.id] ?? selected.mode !== "human"
    : true;

  async function toggleAi() {
    if (!selected) {
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
    setAiEnabledById((current) => ({ ...current, [selected.id]: false }));
    setDraft("");
  }

  async function shareProperty(property: Property) {
    if (!selected) {
      return;
    }
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
        { method: "POST", body: JSON.stringify({ text: buildPropertyShareText(property) }) },
        token,
      );
      setMessagesById((current) => ({
        ...current,
        [selected.id]: [...(current[selected.id] ?? []), { ...created, sharedProperty: property }],
      }));
      setItems((current) =>
        current.map((item) =>
          item.id === selected.id ? { ...item, mode: "human", status: "waiting_human" } : item,
        ),
      );
      setAiEnabledById((current) => ({ ...current, [selected.id]: false }));
      setPropertyShareOpen(false);
    } catch (error) {
      setActionError(readActionError(error));
    }
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

  function appendMessage(
    conversationId: string,
    message: Pick<Message, "direction" | "author_type" | "text"> & { sharedProperty?: Property },
  ) {
    setMessagesById((current) => ({
      ...current,
      [conversationId]: [
        ...(current[conversationId] ?? []),
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
                  </span>
                  <Badge variant={itemAiEnabled ? "success" : "accent"}>
                    {itemAiEnabled ? "IA" : "Equipe"}
                  </Badge>
                </button>
              );
            })}
            {visibleItems.length === 0 ? <div className="empty-state">Nenhuma conversa encontrada.</div> : null}
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
              <button
                className="button-outline"
                onClick={() => setDemandModalOpen(true)}
                type="button"
              >
                <Plus size={15} />
                Cadastrar demanda
              </button>
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
              <strong>Agente de Leads</strong> está {aiEnabled ? "ativo" : "desativado"} nessa conversa.
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
              <strong>{selected?.current_intent ?? "Qualificação de lead"}</strong>
            </div>
          </div>

          <div className="chat-composer">
            <div className="composer-tools">
              <button
                aria-label="Compartilhar imóvel"
                className="icon-button"
                onClick={() => setPropertyShareOpen(true)}
                title="Compartilhar imóvel"
                type="button"
              >
                <Building2 size={17} />
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
        conversationId={selected?.id}
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
                    <button onClick={() => void shareProperty(property)} type="button">
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

const authorLabels: Record<string, string> = {
  ai: "IA",
  customer: "Cliente",
  human: "Equipe",
  system: "Sistema",
};
