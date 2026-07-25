import { useEffect, useState } from "react";
import { request } from "../api/client";
import type { ConversationDetail, Message } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { demoConversationDetails } from "./ConversationsPage";

export function ConversationDetailPage({ id, onBack }: { id: string; onBack: () => void }) {
  const { token } = useAuth();
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [text, setText] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function loadConversation() {
    if (demoConversationDetails[id]) {
      setDetail(demoConversationDetails[id]);
      return;
    }
    setDetail(await request<ConversationDetail>(`/conversations/${id}`, {}, token));
  }

  useEffect(() => {
    void loadConversation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, token]);

  async function setMode(mode: "ai" | "human") {
    setMessage(null);
    try {
      await request(`/conversations/${id}/mode`, {
        method: "PATCH",
        body: JSON.stringify({ mode }),
      }, token);
      await loadConversation();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao alterar modo.");
    }
  }

  async function sendMessage() {
    if (!text.trim()) {
      return;
    }
    setMessage(null);
    try {
      const created = await request<Message>(
        `/conversations/${id}/messages`,
        {
          method: "POST",
          body: JSON.stringify({ text }),
        },
        token,
      );
      setText("");
      setDetail((current) =>
        current ? { ...current, messages: [...current.messages, created] } : current,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao enviar mensagem.");
    }
  }

  return (
    <section className="page-stack">
      <button className="link-button" onClick={onBack} type="button">
        ← Voltar
      </button>
      <header className="page-header">
        <span className="eyebrow">Conversa</span>
        <h1>{detail?.phone ?? "Carregando..."}</h1>
        <p>{detail?.customer_name ?? "Histórico de mensagens da empresa atual."}</p>
      </header>
      <article className="card conversation-toolbar">
        <div>
          <span>Modo atual</span>
          <Badge variant={detail?.mode === "human" ? "accent" : "success"}>{detail?.mode ?? "—"}</Badge>
        </div>
        <div className="toolbar-actions">
          <button className="button-outline" onClick={() => void setMode("ai")} type="button">
            IA
          </button>
          <button className="button-outline" onClick={() => void setMode("human")} type="button">
            Handoff humano
          </button>
        </div>
      </article>
      {message ? <div className="error-box">{message}</div> : null}
      <div className="chat-list">
        {detail?.messages.map((message) => (
          <article className={`message ${message.direction}`} key={message.id}>
            <small>{message.author_type}</small>
            <p>{message.text}</p>
          </article>
        ))}
      </div>
      <article className="card message-composer">
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Enviar mensagem humana pelo canal configurado..."
        />
        <button disabled={!text.trim()} onClick={sendMessage} type="button">
          Enviar mensagem
        </button>
      </article>
    </section>
  );
}
