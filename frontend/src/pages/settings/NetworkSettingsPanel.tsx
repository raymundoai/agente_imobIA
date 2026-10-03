import { FormEvent, useEffect, useState } from "react";
import { Check, Mail, Phone, RefreshCw, Share2, X } from "lucide-react";
import { request } from "../../api/client";
import type { NetworkSettings, Partnership } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Card } from "../../components/Card";
import { openBillingSettings } from "../../components/TrialBanner";

const statusLabels: Record<Partnership["status"], string> = {
  pending: "Aguardando resposta",
  accepted: "Parceria aceita",
  declined: "Recusada",
  cancelled: "Cancelada",
};

export function NetworkSettingsPanel() {
  const { token } = useAuth();
  const role = getTokenClaims(token)?.role;
  const isAdmin = role === "admin";
  const canDecide = role === "admin" || role === "gestor";
  const [settings, setSettings] = useState<NetworkSettings | null>(null);
  const [partnerships, setPartnerships] = useState<{ received: Partnership[]; sent: Partnership[] }>({ received: [], sent: [] });
  const [form, setForm] = useState({ partner_commission_percent: "50", contact_name: "", contact_phone: "", contact_email: "" });
  const [accepted, setAccepted] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [next, list] = await Promise.all([
        request<NetworkSettings>("/network/settings", {}, token),
        request<{ received: Partnership[]; sent: Partnership[] }>("/network/partnerships", {}, token),
      ]);
      setSettings(next);
      setPartnerships(list);
      setForm((current) => ({
        partner_commission_percent: String(next.partner_commission_percent ?? current.partner_commission_percent),
        contact_name: next.contact_name ?? current.contact_name,
        contact_phone: next.contact_phone ?? current.contact_phone,
        contact_email: next.contact_email ?? current.contact_email,
      }));
    } catch (reason) {
      setMessage({ kind: "error", text: reason instanceof Error ? reason.message : "Não foi possível carregar a rede." });
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!accepted && !settings?.member) {
      setMessage({ kind: "error", text: "Leia e aceite o termo para participar da rede." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const next = await request<NetworkSettings>(
        "/network/settings",
        {
          method: "PUT",
          body: JSON.stringify({ ...form, partner_commission_percent: Number(form.partner_commission_percent), accept_terms: true }),
        },
        token,
      );
      setSettings(next);
      setMessage({ kind: "success", text: next.member && settings?.member ? "Configuração da rede salva." : "Bem-vindo à Rede ImmobIA! Agora você pode compartilhar imóveis." });
    } catch (reason) {
      setMessage({ kind: "error", text: reason instanceof Error ? reason.message : "Não foi possível salvar." });
    } finally {
      setBusy(false);
    }
  }

  async function act(item: Partnership, action: "accept" | "decline" | "cancel") {
    const confirmations = {
      accept: `Aceitar a parceria com ${item.counterpart_agency}? Os contatos de parceria das duas imobiliárias serão liberados.`,
      decline: `Recusar o pedido de ${item.counterpart_agency}?`,
      cancel: "Cancelar este pedido de parceria?",
    };
    if (!window.confirm(confirmations[action])) return;
    setBusy(true);
    try {
      await request(`/network/partnerships/${item.id}/${action}`, { method: "POST" }, token);
      await load();
    } catch (reason) {
      setMessage({ kind: "error", text: reason instanceof Error ? reason.message : "Não foi possível concluir." });
    } finally {
      setBusy(false);
    }
  }

  if (!settings) {
    return <Card className="settings-panel-card">{message ? <div className="error-box">{message.text}</div> : <div className="empty-state">Carregando Rede ImmobIA...</div>}</Card>;
  }

  const partnerShare = Number(form.partner_commission_percent) || 0;

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Rede ImmobIA</h2>
          <p>Compartilhe imóveis da sua carteira com outras imobiliárias e encontre parceiros para os seus clientes.</p>
        </div>
        <button className="button-outline" disabled={busy} onClick={() => void load()} type="button">
          <RefreshCw size={14} />
          Atualizar
        </button>
      </div>

      {!settings.eligible ? (
        <div className="info-box network-upsell">
          <span>A Rede ImmobIA está disponível nos planos pagos.</span>
          <button className="link-button" onClick={openBillingSettings} type="button">Ver planos</button>
        </div>
      ) : null}

      {settings.member ? (
        <div className="network-stats">
          <div><strong>{settings.shared_properties}</strong><span>imóveis compartilhados</span></div>
          <div><strong>{settings.pending_received}</strong><span>pedidos aguardando resposta</span></div>
          <div><strong>{settings.partner_commission_percent}%</strong><span>da comissão para o parceiro</span></div>
        </div>
      ) : null}

      <form className="settings-subsection network-form" onSubmit={save}>
        <div>
          <h3>{settings.member ? "Regra de parceria" : "Participar da rede"}</h3>
          <p>A divisão vale para todos os imóveis compartilhados. O contato só aparece para o parceiro depois que vocês aceitarem o pedido.</p>
        </div>
        <fieldset className="settings-form-fieldset" disabled={!isAdmin || !settings.eligible}>
          <div className="form-grid">
            <label>
              Comissão para a imobiliária parceira (%)
              <input max={99} min={1} type="number" value={form.partner_commission_percent} onChange={(event) => setForm({ ...form, partner_commission_percent: event.target.value })} />
              <small className="field-hint">Parceiro {partnerShare}% · Vocês {Math.max(0, 100 - partnerShare)}% da comissão da venda ou locação.</small>
            </label>
            <label>
              Nome para contato
              <input value={form.contact_name} onChange={(event) => setForm({ ...form, contact_name: event.target.value })} />
            </label>
            <label>
              WhatsApp para parcerias
              <input inputMode="tel" value={form.contact_phone} onChange={(event) => setForm({ ...form, contact_phone: event.target.value })} />
            </label>
            <label>
              Email para parcerias
              <input type="email" value={form.contact_email} onChange={(event) => setForm({ ...form, contact_email: event.target.value })} />
            </label>
          </div>
          {!settings.member ? (
            <div className="network-terms">
              <strong>Termo da Rede ImmobIA (versão {settings.terms_version})</strong>
              <p>{settings.terms_text}</p>
              <label className="checkbox-row">
                <input checked={accepted} onChange={(event) => setAccepted(event.target.checked)} type="checkbox" />
                Li e aceito o termo em nome da imobiliária
              </label>
            </div>
          ) : (
            <small className="field-hint">
              Termo aceito em {settings.terms_accepted_at ? new Date(settings.terms_accepted_at).toLocaleDateString("pt-BR") : "—"} (versão {settings.terms_version}).
            </small>
          )}
          {isAdmin && settings.eligible ? (
            <button className="primary-button" disabled={busy} type="submit">
              <Share2 size={15} />
              {settings.member ? "Salvar regra" : "Entrar na Rede ImmobIA"}
            </button>
          ) : null}
        </fieldset>
        {!isAdmin ? <small className="field-hint">Somente o administrador da conta altera a adesão e a comissão.</small> : null}
      </form>

      {message ? <div className={message.kind === "error" ? "error-box" : "inline-feedback"}>{message.text}</div> : null}

      <PartnershipList
        busy={busy}
        canAct={canDecide}
        emptyText="Nenhum pedido recebido ainda."
        items={partnerships.received}
        onAct={act}
        title="Pedidos recebidos"
      />
      <PartnershipList
        busy={busy}
        canAct
        emptyText="Você ainda não pediu parceria. Encontre imóveis da rede no Buscador de imóveis."
        items={partnerships.sent}
        onAct={act}
        title="Pedidos enviados"
      />
    </Card>
  );
}

function PartnershipList({
  title,
  items,
  emptyText,
  canAct,
  busy,
  onAct,
}: {
  title: string;
  items: Partnership[];
  emptyText: string;
  canAct: boolean;
  busy: boolean;
  onAct: (item: Partnership, action: "accept" | "decline" | "cancel") => void;
}) {
  return (
    <div className="settings-subsection">
      <h3>{title}</h3>
      {items.length === 0 ? <p className="field-hint">{emptyText}</p> : null}
      <div className="partnership-list">
        {items.map((item) => (
          <article className={`partnership-card status-${item.status}`} key={item.id}>
            <div className="partnership-main">
              <strong>{item.property_title}</strong>
              <span>
                {item.direction === "received" ? "Pedido de " : "Imóvel de "}
                {item.counterpart_agency} · {item.partner_commission_percent}% para o parceiro ·{" "}
                {new Date(item.created_at).toLocaleDateString("pt-BR")}
              </span>
              {item.message ? <p>“{item.message}”</p> : null}
              {item.counterpart_contact ? (
                <div className="partnership-contact">
                  <strong>{item.counterpart_contact.name}</strong>
                  <a href={`https://wa.me/${item.counterpart_contact.phone.replace(/\D/g, "")}`} rel="noreferrer" target="_blank">
                    <Phone size={13} /> {item.counterpart_contact.phone}
                  </a>
                  <a href={`mailto:${item.counterpart_contact.email}`}>
                    <Mail size={13} /> {item.counterpart_contact.email}
                  </a>
                </div>
              ) : null}
            </div>
            <div className="partnership-side">
              <span className="partnership-status">{statusLabels[item.status]}</span>
              {item.status === "pending" && canAct && item.direction === "received" ? (
                <div className="partnership-actions">
                  <button className="primary-button" disabled={busy} onClick={() => onAct(item, "accept")} type="button"><Check size={14} /> Aceitar</button>
                  <button className="button-outline" disabled={busy} onClick={() => onAct(item, "decline")} type="button"><X size={14} /> Recusar</button>
                </div>
              ) : null}
              {item.status === "pending" && item.direction === "sent" ? (
                <button className="link-button" disabled={busy} onClick={() => onAct(item, "cancel")} type="button">Cancelar pedido</button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
