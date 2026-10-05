import { CheckCircle2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../api/client";
import type { User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Modal } from "./Modal";

export const FEEDBACK_EVENT = "immobia:open-feedback";

export function openFeedback() {
  window.dispatchEvent(new Event(FEEDBACK_EVENT));
}

const KINDS = [
  { value: "problem", label: "Algo não funcionou" },
  { value: "suggestion", label: "Sugestão" },
  { value: "question", label: "Dúvida" },
  { value: "praise", label: "Elogio" },
] as const;

/** Beta feedback: the person describes the case; who they are and where they were go along. */
export function FeedbackModal() {
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [kind, setKind] = useState<(typeof KINDS)[number]["value"]>("problem");
  const [message, setMessage] = useState("");
  const [phone, setPhone] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onOpen = () => {
      setOpen(true);
      setSent(false);
      setError(null);
      request<User>("/users/me", {}, token).then(setUser).catch(() => setUser(null));
    };
    window.addEventListener(FEEDBACK_EVENT, onOpen);
    return () => window.removeEventListener(FEEDBACK_EVENT, onOpen);
  }, [token]);

  if (!open) return null;
  const page = `${window.location.pathname}${window.location.search}`;

  async function send() {
    setSending(true);
    setError(null);
    try {
      await request(
        "/feedback",
        { method: "POST", body: JSON.stringify({ kind, message: message.trim(), page, contact_phone: phone.trim() || null }) },
        token,
      );
      setSent(true);
      setMessage("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível enviar. Tente de novo.");
    } finally {
      setSending(false);
    }
  }

  const close = () => setOpen(false);
  return (
    <Modal
      description={sent ? undefined : "Conte o que aconteceu ou o que podemos melhorar. Lemos tudo que chega por aqui."}
      footer={
        sent ? (
          <button className="primary-button" onClick={close} type="button">Fechar</button>
        ) : (
          <>
            <button className="secondary-button" onClick={close} type="button">Cancelar</button>
            <button className="primary-button" disabled={sending || message.trim().length < 5} onClick={() => void send()} type="button">
              {sending ? <><Loader2 className="spin" size={15} /> Enviando…</> : "Enviar"}
            </button>
          </>
        )
      }
      onClose={close}
      title={sent ? "Recebemos, obrigado!" : "Enviar feedback"}
    >
      {sent ? (
        <div className="qr-state qr-success">
          <CheckCircle2 size={40} />
          <span>Sua mensagem chegou à equipe da ImmobIA. Se for um problema, retornamos pelo seu e-mail ou WhatsApp.</span>
        </div>
      ) : (
        <div className="feedback-form">
          <div className="segmented" role="radiogroup" aria-label="Tipo">
            {KINDS.map((option) => (
              <button
                aria-checked={kind === option.value}
                className={kind === option.value ? "active" : undefined}
                key={option.value}
                onClick={() => setKind(option.value)}
                role="radio"
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
          <label>
            O que aconteceu?
            <textarea
              autoFocus
              onChange={(event) => setMessage(event.target.value)}
              placeholder={kind === "problem" ? "Ex.: cliquei em Conectar no WhatsApp e o QR Code sumiu antes de eu ler." : "Escreva com suas palavras."}
              rows={5}
              value={message}
            />
          </label>
          <label>
            <span>WhatsApp para retorno <span className="optional">(opcional)</span></span>
            <input inputMode="tel" onChange={(event) => setPhone(event.target.value)} placeholder="(51) 99999-9999" value={phone} />
          </label>
          <p className="feedback-context">
            Vai junto: {user ? `${user.name} (${user.email})` : "seu nome e e-mail"}, a empresa e a tela atual ({page}).
          </p>
          {error ? <div className="error-box" role="alert">{error}</div> : null}
        </div>
      )}
    </Modal>
  );
}
