import {
  Building2,
  Clock,
  Download,
  FileText,
  Mic,
  MessageSquare,
  Paperclip,
  Phone,
  Plus,
  Search,
  Send,
  Square,
  TriangleAlert,
  UserCheck,
  UserRound,
  UsersRound,
  X,
} from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { request, requestBlob } from "../api/client";
import type { Contact, Conversation, ConversationDetail, LeadDemand, Message, Property, PropertyImage, Tenant } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { getTokenClaims } from "../auth/tokenClaims";
import { Badge } from "../components/Badge";
import { DemandModal } from "../components/DemandModal";
import { mergeUserContactTags, TagInput, userContactTags } from "../components/TagInput";
import { formatCurrency, labelOrDash } from "../lib/format";

type ChatMessage = Message & { sharedProperty?: Property };

export function ConversationsPage() {
  const { token } = useAuth();
  const claims = getTokenClaims(token);
  const [items, setItems] = useState<Conversation[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [profilePictures, setProfilePictures] = useState<Record<string, string | null>>({});
  const [contactEditorOpen, setContactEditorOpen] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [conversationScope, setConversationScope] = useState<"direct" | "groups">("direct");
  const [draft, setDraft] = useState("");
  const [propertyShareOpen, setPropertyShareOpen] = useState(false);
  const [propertyShareScope, setPropertyShareScope] = useState<"internal" | "external">("internal");
  const [demandModalOpen, setDemandModalOpen] = useState(false);
  const [properties, setProperties] = useState<Property[]>([]);
  const [propertyCovers, setPropertyCovers] = useState<Record<string, string>>({});
  const propertyCoverUrls = useRef<Record<string, string>>({});
  const [aiEnabledById, setAiEnabledById] = useState<Record<string, boolean>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [messagesById, setMessagesById] = useState<Record<string, ChatMessage[]>>({});
  const [listLoading, setListLoading] = useState(true);
  const [togglingAi, setTogglingAi] = useState(false);
  const [sendingMedia, setSendingMedia] = useState(false);
  const [recording, setRecording] = useState(false);
  const [globalAgentActive, setGlobalAgentActive] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordingStreamRef = useRef<MediaStream | null>(null);
  const chatListRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void Promise.all([
      request<Conversation[]>("/conversations", {}, token),
      request<Contact[]>("/contacts", {}, token),
    ])
      .then(([conversations, loadedContacts]) => {
        const nextItems = conversations;
        setItems(nextItems);
        setContacts(loadedContacts);
        setSelectedId((current) =>
          nextItems.some((item) => item.id === current) ? current : (nextItems[0]?.id ?? ""),
        );
      })
      .catch((error) => {
        setItems([]);
        setActionError(readActionError(error));
      })
      .finally(() => setListLoading(false));
  }, [token]);

  useEffect(() => {
    let active = true;
    const sync = async () => {
      try {
        const [conversations, loadedContacts] = await Promise.all([
          request<Conversation[]>("/conversations", {}, token),
          request<Contact[]>("/contacts", {}, token),
        ]);
        if (!active) return;
        setItems(conversations);
        setContacts(loadedContacts);
        setSelectedId((current) =>
          conversations.some((item) => item.id === current)
            ? current
            : (conversations[0]?.id ?? ""),
        );
        if (selectedId && conversations.some((item) => item.id === selectedId)) {
          const detail = await request<ConversationDetail>(
            `/conversations/${selectedId}`,
            {},
            token,
          );
          if (!active) return;
          setMessagesById((current) => ({ ...current, [selectedId]: detail.messages }));
          setItems((current) =>
            current.map((item) => (item.id === selectedId ? mergeConversation(item, detail) : item)),
          );
        }
      } catch {
        // A próxima rodada tenta novamente; erros de ações continuam visíveis no composer.
      }
    };
    const interval = window.setInterval(() => void sync(), 3000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [selectedId, token]);

  useEffect(() => {
    if (!claims?.tenantId) return;
    let active = true;
    const syncAgentStatus = async () => {
      try {
        const tenant = await request<Tenant>(`/tenants/${claims.tenantId}`, {}, token);
        if (!active) return;
        const agents = tenant.settings.agents as
          | { leads?: { status?: string } }
          | undefined;
        setGlobalAgentActive(
          String(agents?.leads?.status ?? "active").toLowerCase() !== "inactive",
        );
      } catch {
        // Mantém o último estado conhecido e tenta novamente na próxima rodada.
      }
    };
    void syncAgentStatus();
    const interval = window.setInterval(() => void syncAgentStatus(), 10000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [claims?.tenantId, token]);

  useEffect(() => {
    let active = true;
    void request<Property[]>("/properties", {}, token)
      .then(async (loaded) => {
        if (!active) return;
        setProperties(loaded);
        const entries = await Promise.all(loaded.map(async (property) => {
          try {
            const images = await request<PropertyImage[]>(`/properties/${property.id}/images`, {}, token);
            const primary = images.find((image) => image.is_primary) ?? images[0];
            if (!primary) return null;
            const blob = await requestBlob(primary.display_url, token);
            return [property.id, URL.createObjectURL(blob)] as const;
          } catch {
            return null;
          }
        }));
        const next = Object.fromEntries(
          entries.filter(Boolean) as Array<readonly [string, string]>,
        );
        if (!active) {
          Object.values(next).forEach(URL.revokeObjectURL);
          return;
        }
        Object.values(propertyCoverUrls.current).forEach(URL.revokeObjectURL);
        propertyCoverUrls.current = next;
        setPropertyCovers(next);
      })
      .catch((error) => {
        if (active) {
          setProperties([]);
          setActionError(readActionError(error));
        }
      });
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => () => {
    Object.values(propertyCoverUrls.current).forEach(URL.revokeObjectURL);
    propertyCoverUrls.current = {};
  }, []);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    void request<ConversationDetail>(`/conversations/${selectedId}`, {}, token)
      .then((detail) => {
        setMessagesById((current) => ({ ...current, [selectedId]: detail.messages }));
        setItems((current) =>
          current.map((item) => (item.id === selectedId ? mergeConversation(item, detail) : item)),
        );
      })
      .catch((error) => setActionError(readActionError(error)));
  }, [selectedId, token]);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      const matchesScope =
        conversationScope === "groups" ? item.is_group : !item.is_group;
      const matchesSearch =
        !normalized ||
        [
          item.customer_name,
          item.phone,
          item.status,
          item.mode,
        ].some((value) => String(value ?? "").toLowerCase().includes(normalized));
      return matchesScope && matchesSearch;
    });
  }, [conversationScope, items, query]);

  const selected = visibleItems.find((item) => item.id === selectedId) ?? visibleItems[0];
  const selectedContact = selected?.contact_id
    ? contacts.find((contact) => contact.id === selected.contact_id) ?? null
    : null;
  const selectedMessages = selected ? messagesById[selected.id] ?? [] : [];
  const aiEnabled = selected
    ? selected.is_group
      ? false
      : aiEnabledById[selected.id] ?? selected.mode !== "human"
    : true;

  useLayoutEffect(() => {
    const chatList = chatListRef.current;
    if (!chatList || !selected?.id) return;

    const scrollToLatest = () => {
      chatList.scrollTop = chatList.scrollHeight;
    };
    scrollToLatest();
    const frame = window.requestAnimationFrame(scrollToLatest);
    const mediaLayoutTimer = window.setTimeout(scrollToLatest, 180);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(mediaLayoutTimer);
    };
  }, [selected?.id, selectedMessages.length]);

  useEffect(() => {
    const contactIds = [...new Set(
      visibleItems
        .filter((item) => !item.is_group && item.contact_id)
        .map((item) => item.contact_id as string),
    )].filter((contactId) => !(contactId in profilePictures));
    if (!contactIds.length) return;
    let active = true;
    void Promise.all(contactIds.map(async (contactId) => {
      try {
        const { url } = await request<{ url: string | null }>(
          `/contacts/${contactId}/profile-picture`,
          {},
          token,
        );
        return [contactId, url] as const;
      } catch {
        return [contactId, null] as const;
      }
    })).then((entries) => {
      if (active) {
        setProfilePictures((current) => ({ ...current, ...Object.fromEntries(entries) }));
      }
    });
    return () => {
      active = false;
    };
  }, [profilePictures, token, visibleItems]);

  function handleContactSaved(saved: Contact) {
    setContacts((current) => current.map((contact) => contact.id === saved.id ? saved : contact));
    setItems((current) => current.map((conversation) =>
      conversation.contact_id === saved.id
        ? { ...conversation, customer_name: saved.name, phone: saved.phone }
        : conversation
    ));
    setContactEditorOpen(false);
  }

  async function toggleAi() {
    if (!selected) {
      return;
    }
    setActionError(null);
    setTogglingAi(true);
    try {
      const updated = await request<Conversation>(
        `/conversations/${selected.id}/mode`,
        { method: "PATCH", body: JSON.stringify({ mode: aiEnabled ? "human" : "ai" }) },
        token,
      );
      setItems((current) =>
        current.map((item) => (item.id === updated.id ? mergeConversation(item, updated) : item)),
      );
      setAiEnabledById((current) => ({ ...current, [selected.id]: updated.mode !== "human" }));
    } catch (error) {
      setActionError(readActionError(error));
    } finally {
      setTogglingAi(false);
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
        current.map((item) => (item.id === updated.id ? mergeConversation(item, updated) : item)),
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

  async function ensureHumanMode(conversation: Conversation) {
    if (conversation.mode === "human") return;
    const updated = await request<Conversation>(
      `/conversations/${conversation.id}/mode`,
      { method: "PATCH", body: JSON.stringify({ mode: "human" }) },
      token,
    );
    setItems((current) =>
      current.map((item) => (item.id === updated.id ? mergeConversation(item, updated) : item)),
    );
    setAiEnabledById((current) => ({ ...current, [conversation.id]: false }));
  }

  async function sendMedia(file: File) {
    if (!selected) return;
    setActionError(null);
    setSendingMedia(true);
    try {
      await ensureHumanMode(selected);
      const form = new FormData();
      form.append("file", file);
      if (draft.trim()) form.append("caption", draft.trim());
      const created = await request<Message>(
        `/conversations/${selected.id}/media`,
        { method: "POST", body: form },
        token,
      );
      setMessagesById((current) => ({
        ...current,
        [selected.id]: [...(current[selected.id] ?? []), created],
      }));
      setDraft("");
    } catch (error) {
      setActionError(readActionError(error));
    } finally {
      setSendingMedia(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const recorder = new MediaRecorder(stream);
      recordingStreamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        recordingStreamRef.current = null;
        recorderRef.current = null;
        setRecording(false);
        const type = recorder.mimeType || "audio/webm";
        const extension = type.includes("ogg") ? "ogg" : "webm";
        void sendMedia(new File(chunks, `audio-${Date.now()}.${extension}`, { type }));
      };
      recorder.start();
      setRecording(true);
    } catch {
      setActionError("Não foi possível acessar o microfone. Confira a permissão do navegador.");
    }
  }

  useEffect(() => () => {
    recorderRef.current?.stop();
    recordingStreamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

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
          attachments: [],
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
              placeholder="Buscar por cliente, identificação ou status"
              value={query}
            />
          </label>
          <div className="conversation-scope" role="tablist" aria-label="Tipo de conversa">
            <button
              aria-selected={conversationScope === "direct"}
              className={conversationScope === "direct" ? "active" : ""}
              onClick={() => {
                setConversationScope("direct");
                setSelectedId(items.find((item) => !item.is_group)?.id ?? "");
              }}
              role="tab"
              type="button"
            >
              <MessageSquare size={15} />
              Individuais
            </button>
            <button
              aria-selected={conversationScope === "groups"}
              className={conversationScope === "groups" ? "active" : ""}
              onClick={() => {
                setConversationScope("groups");
                setSelectedId(items.find((item) => item.is_group)?.id ?? "");
              }}
              role="tab"
              type="button"
            >
              <UsersRound size={15} />
              Grupos
            </button>
          </div>
          <div className="conversation-list">
            {listLoading ? <div className="empty-state" aria-live="polite">Carregando conversas...</div> : null}
            {!listLoading && visibleItems.map((item) => {
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
                    {item.is_group ? (
                      <UsersRound size={16} />
                    ) : item.contact_id && profilePictures[item.contact_id] ? (
                      <img alt="" src={profilePictures[item.contact_id] ?? ""} />
                    ) : (
                      <UserRound size={16} />
                    )}
                  </span>
                  <span>
                    <strong>{item.group_name ?? item.customer_name ?? item.phone}</strong>
                    <small className="conversation-preview">{lastMessagePreview(item)}</small>
                  </span>
                  <span className="conversation-item-status">
                    <Badge variant={itemAiEnabled ? "success" : "accent"}>
                      {item.is_group ? "Grupo" : itemAiEnabled ? "IA" : "Equipe"}
                    </Badge>
                    <ChannelMark channel={item.channel} />
                  </span>
                </button>
              );
            })}
            {!listLoading && visibleItems.length === 0 ? <div className="empty-state">Nenhuma conversa encontrada.</div> : null}
          </div>
        </aside>

        <article className="chat-panel">
          <div className="chat-panel-header">
            <div className="chat-contact-heading">
              <span className="conversation-avatar chat-contact-avatar">
                {selected?.is_group ? (
                  <UsersRound size={19} />
                ) : profilePictures[selectedContact?.id ?? ""] ? (
                  <img alt="" src={profilePictures[selectedContact?.id ?? ""] ?? ""} />
                ) : (
                  <UserRound size={19} />
                )}
              </span>
              <div>
                <div className="chat-contact-title">
                  <button
                    className="contact-name-button"
                    disabled={!selectedContact}
                    onClick={() => setContactEditorOpen(true)}
                    title={selectedContact ? "Abrir dados do contato" : undefined}
                    type="button"
                  >
                    {selected?.group_name ?? selectedContact?.name ?? selected?.customer_name ?? selected?.phone ?? "Conversa"}
                  </button>
                  {!selected?.is_group ? (
                    <span className="interest-chip">
                      {selectedContact?.interest || selected?.current_intent || "Interesse não informado"}
                    </span>
                  ) : null}
                </div>
              <p>
                {selected?.is_group ? <UsersRound size={14} /> : <Phone size={14} />}
                {selected?.is_group ? "Grupo do WhatsApp" : selected?.phone ?? "Sem telefone"}
                <span>·</span>
                {selected?.channel === "telegram" ? "Telegram" : "WhatsApp"}
                <Clock size={14} />
                {selected?.status === "waiting_human" ? "Aguardando equipe" : "Em atendimento"}
              </p>
              </div>
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
              aria-label={
                selected
                  ? aiEnabled
                    ? "Desativar agente"
                    : "Ativar agente"
                  : "Selecione uma conversa para controlar o agente"
              }
              disabled={!selected || selected.is_group || togglingAi}
              onClick={() => void toggleAi()}
              type="button"
            >
              <span />
            </button>
            <p className="agent-status">
              <strong>Agente de Leads</strong>{" "}
              {togglingAi
                ? "está alterando o estado..."
                : selected?.is_group
                  ? "não atua em grupos; o atendimento é sempre humano."
                  : selected
                  ? `está ${aiEnabled ? "ativo" : "desativado"} nessa conversa.`
                  : "pode ser controlado após selecionar uma conversa."}
            </p>
            {selected && !selected.is_group && aiEnabled && !globalAgentActive ? (
              <span className="agent-global-warning" role="status">
                <TriangleAlert size={14} />
                Agente inativo nas configurações
              </span>
            ) : null}
          </div>
          {actionError ? <div className="error-box">{actionError}</div> : null}

          <div className="chat-list embedded" ref={chatListRef}>
            {selectedMessages.map((message) => (
              <article className={`message ${message.direction}`} key={message.id}>
                <small>
                  {message.sender_name && message.direction === "inbound"
                    ? message.sender_name
                    : authorLabels[message.author_type] ?? message.author_type}
                </small>
                {message.text ? <p>{message.text}</p> : null}
                {message.attachments?.map((attachment, index) => (
                  <MessageAttachment
                    attachment={attachment}
                    conversationId={selected?.id ?? ""}
                    index={index}
                    key={`${message.id}-${index}`}
                    messageId={message.id}
                    token={token}
                  />
                ))}
                {message.sharedProperty ? <SharedPropertyPreview imageUrl={propertyCovers[message.sharedProperty.id]} property={message.sharedProperty} /> : null}
              </article>
            ))}
          </div>

          <div className="chat-composer">
            <div className="composer-tools">
              <input
                accept="image/*,video/mp4,audio/*,.pdf,.txt,.doc,.docx"
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void sendMedia(file);
                }}
                ref={fileInputRef}
                type="file"
              />
              <button
                aria-label="Anexar arquivo, imagem ou áudio"
                className="icon-button"
                disabled={!selected || sendingMedia}
                onClick={() => fileInputRef.current?.click()}
                title="Anexar arquivo, imagem ou áudio"
                type="button"
              >
                <Paperclip size={17} />
              </button>
              <button
                aria-label={recording ? "Parar e enviar gravação" : "Gravar áudio"}
                className={recording ? "icon-button recording" : "icon-button"}
                disabled={!selected || sendingMedia}
                onClick={() => void toggleRecording()}
                title={recording ? "Parar e enviar gravação" : "Gravar áudio"}
                type="button"
              >
                {recording ? <Square size={16} /> : <Mic size={17} />}
              </button>
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
              disabled={!draft.trim() || sendingMedia}
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
      {contactEditorOpen && selectedContact ? (
        <ContactEditorSidebar
          channel={selected?.channel}
          contact={selectedContact}
          conversationId={selected?.id}
          onClose={() => setContactEditorOpen(false)}
          onSaved={handleContactSaved}
          token={token}
        />
      ) : null}
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

            <div className="conversation-scope property-share-scope" role="tablist" aria-label="Origem do imóvel">
              <button
                aria-selected={propertyShareScope === "internal"}
                className={propertyShareScope === "internal" ? "active" : ""}
                onClick={() => setPropertyShareScope("internal")}
                role="tab"
                type="button"
              >
                Carteira própria
              </button>
              <button
                aria-selected={propertyShareScope === "external"}
                className={propertyShareScope === "external" ? "active" : ""}
                onClick={() => setPropertyShareScope("external")}
                role="tab"
                type="button"
              >
                Captados / externos
              </button>
            </div>

            {properties.some((property) =>
              propertyShareScope === "internal" ? property.source === "manual" : property.source !== "manual"
            ) ? (
              <div className="property-share-list">
                {properties.filter((property) =>
                  propertyShareScope === "internal" ? property.source === "manual" : property.source !== "manual"
                ).map((property) => (
                  <article className="property-share-item" key={property.id}>
                    <PropertyShareThumb imageUrl={propertyCovers[property.id]} property={property} />
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
                {propertyShareScope === "internal"
                  ? "Nenhum imóvel da carteira própria para compartilhar."
                  : "Nenhum imóvel captado ou externo para compartilhar."}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}

function SharedPropertyPreview({ property, imageUrl }: { property: Property; imageUrl?: string }) {
  return (
    <div className="shared-property-preview">
      {imageUrl ? (
        <div className="shared-property-images">
          <img alt={`${property.title} - foto principal`} src={imageUrl} />
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

function MessageAttachment({
  attachment,
  conversationId,
  index,
  messageId,
  token,
}: {
  attachment: Message["attachments"][number];
  conversationId: string;
  index: number;
  messageId: string;
  token: string | null;
}) {
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const source = attachment.storage_key
    ? `/conversations/${conversationId}/messages/${messageId}/media/${index}`
    : null;

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    if (!source) return;
    void requestBlob(source, token)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setLocalUrl(objectUrl);
      })
      .catch(() => setLocalUrl(null));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source, token]);

  const url = localUrl ?? attachment.url ?? null;
  const label = attachment.fileName ?? mediaLabel(attachment.type);
  if (attachment.type === "image" || attachment.type === "sticker") {
    return url ? (
      <img
        alt={attachment.type === "sticker" ? "Figurinha" : label}
        className={attachment.type === "sticker" ? "message-sticker" : "message-image"}
        loading="lazy"
        src={url}
      />
    ) : <span className="media-unavailable">Imagem recebida (prévia indisponível)</span>;
  }
  if (attachment.type === "audio") {
    return url ? <audio className="message-audio" controls preload="metadata" src={url} /> :
      <span className="media-unavailable">Áudio recebido (prévia indisponível)</span>;
  }
  if (attachment.type === "video") {
    return url ? <video className="message-video" controls preload="metadata" src={url} /> :
      <span className="media-unavailable">Vídeo recebido (prévia indisponível)</span>;
  }
  return url ? (
    <a className="message-document" download={label} href={url} rel="noreferrer" target="_blank">
      <FileText size={18} />
      <span>{label}</span>
      <Download size={16} />
    </a>
  ) : (
    <span className="media-unavailable"><FileText size={16} /> {label}</span>
  );
}

function mediaLabel(type: string) {
  return type === "document" ? "Documento" : "Arquivo";
}

function lastMessagePreview(conversation: Conversation) {
  const text = conversation.last_message_text?.trim();
  const attachment = conversation.last_message_attachments?.[0];
  const content = text || (attachment ? attachmentPreviewLabel(attachment.type) : "Sem mensagens");
  return `${conversation.last_message_direction === "outbound" ? "Você: " : ""}${content}`;
}

function attachmentPreviewLabel(type: string) {
  const labels: Record<string, string> = {
    audio: "🎤 Áudio",
    document: "📄 Documento",
    image: "📷 Foto",
    photo: "📷 Foto",
    sticker: "Figurinha",
    video: "🎥 Vídeo",
    voice: "🎤 Áudio",
  };
  return labels[type] ?? "📎 Arquivo";
}

function ChannelMark({ channel }: { channel?: "whatsapp" | "telegram" }) {
  const isTelegram = channel === "telegram";
  return (
    <span
      aria-label={isTelegram ? "Telegram" : "WhatsApp"}
      className={`channel-mark ${isTelegram ? "telegram" : "whatsapp"}`}
      title={isTelegram ? "Telegram" : "WhatsApp"}
    >
      {isTelegram ? <Send size={12} /> : <Phone size={12} />}
    </span>
  );
}

function PropertyShareThumb({ property, imageUrl }: { property: Property; imageUrl?: string }) {
  return (
    <div className="property-share-thumb">
      {imageUrl ? <img alt={property.title} src={imageUrl} /> : <Building2 size={20} />}
    </div>
  );
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

  return [
    `🏠 ${property.title}`,
    location ? `📍 ${location}` : null,
    details.join(" · "),
  ].filter(Boolean).join("\n");
}

function mergeConversation(current: Conversation, incoming: Conversation): Conversation {
  const incomingHasPreview = Boolean(
    incoming.last_message_text?.trim() || incoming.last_message_attachments?.length,
  );
  if (incomingHasPreview || !current.last_message_text && !current.last_message_attachments?.length) {
    return { ...current, ...incoming };
  }
  return {
    ...current,
    ...incoming,
    last_message_text: current.last_message_text,
    last_message_attachments: current.last_message_attachments,
    last_message_direction: current.last_message_direction,
  };
}

function readActionError(error: unknown) {
  return error instanceof Error ? error.message : "Não foi possível concluir a ação.";
}

function ContactEditorSidebar({
  channel,
  contact,
  conversationId,
  onClose,
  onSaved,
  token,
}: {
  channel?: Conversation["channel"];
  contact: Contact;
  conversationId?: string;
  onClose: () => void;
  onSaved: (contact: Contact) => void;
  token: string | null;
}) {
  const [form, setForm] = useState(contact);
  const [demand, setDemand] = useState<LeadDemand | null>(null);
  const [qualification, setQualification] = useState<LeadDemand["status"]>("open");
  const [qualificationLoading, setQualificationLoading] = useState(contact.kind === "lead");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(contact);
    setDemand(null);
    setQualification("open");
    if (contact.kind !== "lead") {
      setQualificationLoading(false);
      return;
    }
    let active = true;
    setQualificationLoading(true);
    void request<LeadDemand[]>(`/leads/demands?limit=20&contact_id=${contact.id}`, {}, token)
      .then((demands) => {
        if (!active) return;
        const current = demands.find((item) => item.status !== "closed") ?? demands[0] ?? null;
        setDemand(current);
        setQualification(current?.status ?? "open");
      })
      .catch((caught) => {
        if (active) setError(readActionError(caught));
      })
      .finally(() => {
        if (active) setQualificationLoading(false);
      });
    return () => {
      active = false;
    };
  }, [contact.id, contact.kind, token]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = await request<Contact>(
        `/contacts/${contact.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            name: form.name,
            phone: form.phone,
            email: form.email || null,
            kind: form.kind,
            status: form.status,
            tags: form.tags,
            interest: form.interest || null,
            notes: form.notes || null,
          }),
        },
        token,
      );
      if (contact.kind === "lead" && !qualificationLoading) {
        if (demand && demand.status !== qualification) {
          await request<LeadDemand>(
            `/leads/demands/${demand.id}`,
            { method: "PATCH", body: JSON.stringify({ status: qualification }) },
            token,
          );
        } else if (!demand && qualification !== "open") {
          await request<LeadDemand>(
            "/leads/demands",
            {
              method: "POST",
              body: JSON.stringify({
                lead_name: saved.name,
                phone: saved.phone,
                status: qualification,
                conversation_id: conversationId ?? null,
              }),
            },
            token,
          );
        }
      }
      onSaved(saved);
    } catch (caught) {
      setError(readActionError(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button aria-label="Fechar dados do contato" className="contact-drawer-backdrop" onClick={onClose} type="button" />
      <aside aria-label="Dados do contato" className="contact-drawer">
        <div className="contact-detail-header">
          <div>
            <span className="eyebrow">Contato</span>
            <h2>{contact.name}</h2>
          </div>
          <button aria-label="Fechar" className="icon-button" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>
        <div className="form-grid">
          <div className="contact-channel-field form-span-2">
            <span>Canal</span>
            <strong><ChannelMark channel={channel} />{channel === "telegram" ? "Telegram" : "WhatsApp"}</strong>
          </div>
          <label className="form-span-2">Nome<input onChange={(event) => setForm({ ...form, name: event.target.value })} value={form.name} /></label>
          <label className="form-span-2">Qualificação do lead
            <select
              disabled={contact.kind !== "lead" || qualificationLoading}
              onChange={(event) => setQualification(event.target.value as LeadDemand["status"])}
              value={qualification}
            >
              <option value="open">Não qualificado</option>
              <option value="qualified">Qualificado</option>
              <option value="in_progress">Em negociação</option>
              <option value="closed">Encerrado</option>
            </select>
            {contact.kind !== "lead" ? <small>A qualificação se aplica somente a contatos do tipo lead.</small> : qualificationLoading ? <small>Carregando qualificação...</small> : null}
          </label>
          <label className="form-span-2">Interesse<input onChange={(event) => setForm({ ...form, interest: event.target.value })} value={form.interest ?? ""} /></label>
          <label>Telefone<input disabled value={form.phone} /></label>
          <label>Email<input onChange={(event) => setForm({ ...form, email: event.target.value })} type="email" value={form.email ?? ""} /></label>
          <label className="form-span-2">Tags
            <TagInput
              onChange={(tags) => setForm({ ...form, tags: mergeUserContactTags(form.tags, tags) })}
              tags={userContactTags(form.tags)}
            />
            <small>Pressione espaço, Enter ou vírgula para criar cada tag.</small>
          </label>
          <label className="form-span-2">Observações<textarea onChange={(event) => setForm({ ...form, notes: event.target.value })} value={form.notes ?? ""} /></label>
        </div>
        {error ? <div className="error-box">{error}</div> : null}
        <div className="settings-actions">
          <span />
          <button disabled={saving || qualificationLoading || !form.name.trim()} onClick={() => void save()} type="button">
            {saving ? "Salvando..." : "Salvar alterações"}
          </button>
        </div>
      </aside>
    </>
  );
}

const authorLabels: Record<string, string> = {
  ai: "IA",
  customer: "Cliente",
  human: "Equipe",
  system: "Sistema",
};
