import { Check, Database, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { IntegrationSetupSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Card } from "../../components/Card";
import { ConnectionCard, ConnectionSections } from "../../components/ConnectionCard";
import { Modal } from "../../components/Modal";

const DESCRIPTIONS: Record<string, string> = {
  kenlo: "Traga a carteira de imóveis e os leads do Kenlo para o ImmobIA.",
  tecimob: "Sincronize os imóveis publicados no seu site Tecimob.",
  jetimob: "Importe imóveis e contatos do CRM Jetimob.",
  orulo: "Ofereça lançamentos de construtoras parceiras da Órulo.",
};

export function IntegrationsSettingsPanel() {
  const { token } = useAuth();
  const role = getTokenClaims(token)?.role;
  const canManage = role === "admin" || role === "gestor";
  const [items, setItems] = useState<IntegrationSetupSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openProvider, setOpenProvider] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    request<IntegrationSetupSummary[]>("/integrations/setup", {}, token)
      .then((catalog) => {
        setItems(catalog);
        setError(null);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Falha ao carregar integrações."))
      .finally(() => setLoading(false));
  }, [token]);

  const opened = items.find((item) => item.provider === openProvider) ?? null;
  const card = (item: IntegrationSetupSummary) => (
    <ConnectionCard
      description={DESCRIPTIONS[item.provider] ?? item.target_resources.join(", ")}
      icon={<Database size={20} />}
      key={item.provider}
      name={item.name}
      onOpen={() => setOpenProvider(item.provider)}
      state={item.status === "connected" ? "connected" : item.status === "not_configured" ? "soon" : "pending"}
    />
  );

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Integrações</h2>
          <p>Conecte o ImmobIA aos sistemas que a imobiliária já usa, como CRMs e portais.</p>
        </div>
      </div>
      {loading ? <div className="empty-state" aria-live="polite"><Loader2 className="spin-icon" size={18} /> Carregando integrações...</div> : null}
      {error ? <div className="error-box" role="alert">{error}</div> : null}
      {!loading && !error ? (
        <ConnectionSections
          connected={items.filter((item) => item.status === "connected").map(card)}
          others={items.filter((item) => item.status !== "connected").map(card)}
          othersTitle="Em breve"
        />
      ) : null}
      {opened ? (
        <IntegrationModal
          canManage={canManage}
          item={opened}
          onClose={() => setOpenProvider(null)}
          onSaved={(updated) => setItems((current) => current.map((item) => (item.provider === updated.provider ? updated : item)))}
          token={token}
        />
      ) : null}
    </Card>
  );
}

function IntegrationModal({
  item,
  canManage,
  token,
  onClose,
  onSaved,
}: {
  item: IntegrationSetupSummary;
  canManage: boolean;
  token: string | null;
  onClose: () => void;
  onSaved: (item: IntegrationSetupSummary) => void;
}) {
  const registered = item.status !== "not_configured";
  const [notes, setNotes] = useState(item.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  async function register() {
    setSaving(true);
    setError(null);
    try {
      const updated = await request<IntegrationSetupSummary>(
        "/integrations/setup",
        { method: "POST", body: JSON.stringify({ provider: item.provider, notes: notes.trim() || null }) },
        token,
      );
      onSaved(updated);
      setJustSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível registrar o interesse.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      description={DESCRIPTIONS[item.provider] ?? item.category}
      footer={
        justSaved ? (
          <button className="primary-button" onClick={onClose} type="button">Concluir</button>
        ) : (
          <>
            <button className="secondary-button" onClick={onClose} type="button">Fechar</button>
            {canManage ? (
              <button className="primary-button" disabled={saving} onClick={() => void register()} type="button">
                {saving ? <><Loader2 className="spin-icon" size={15} /> Enviando...</> : registered ? "Atualizar pedido" : "Quero essa integração"}
              </button>
            ) : null}
          </>
        )
      }
      onClose={onClose}
      title={item.name}
    >
      {justSaved ? (
        <div className="qr-state qr-success">
          <Check size={36} />
          <strong>Pedido registrado</strong>
          <span>Avisamos você assim que a integração com {item.name} estiver disponível.</span>
        </div>
      ) : (
        <div className="integration-modal-body">
          <p className="integration-soon-note">
            Esta integração ainda está em desenvolvimento.
            {registered ? " Você já pediu para ser avisado." : " Registre o interesse e avisamos quando ela chegar."}
          </p>
          <div>
            <h3 className="connection-section-title">O que vai sincronizar</h3>
            <ul className="integration-resources">
              {item.target_resources.map((resource) => <li key={resource}><Check size={14} /> {resource[0].toUpperCase() + resource.slice(1)}</li>)}
            </ul>
          </div>
          {canManage ? (
            <label>
              <span>Como você usa o {item.name}? <span className="optional">(opcional)</span></span>
              <textarea
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Ex.: é a origem oficial da nossa carteira; queremos os imóveis ativos aqui."
                rows={3}
                value={notes}
              />
            </label>
          ) : (
            <p className="connection-hint">Somente administradores e gestores podem pedir integrações.</p>
          )}
          {error ? <div className="error-box" role="alert">{error}</div> : null}
        </div>
      )}
    </Modal>
  );
}
