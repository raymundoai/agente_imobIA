import { Cable, Database, Loader2, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { IntegrationSetupSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";

export function IntegrationsSettingsPanel({
  onDirtyChange,
}: {
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { token } = useAuth();
  const claims = useMemo(() => getTokenClaims(token), [token]);
  const [items, setItems] = useState<IntegrationSetupSummary[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error">("success");
  const canManage = claims?.role === "admin" || claims?.role === "gestor";
  const selected = items.find((item) => item.provider === selectedProvider) ?? null;
  const dirty = Boolean(selected && notes !== (selected.notes ?? ""));

  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    request<IntegrationSetupSummary[]>("/integrations/setup", {}, token)
      .then((catalog) => {
        setItems(catalog);
        setSelectedProvider((current) =>
          current && catalog.some((item) => item.provider === current)
            ? current
            : catalog[0]?.provider ?? null,
        );
        setMessage(null);
      })
      .catch((error) => {
        setMessage(error instanceof Error ? error.message : "Falha ao carregar integrações.");
        setMessageKind("error");
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    setNotes(selected?.notes ?? "");
  }, [selected?.notes, selected?.provider]);

  function selectIntegration(item: IntegrationSetupSummary) {
    if (dirty && !window.confirm("Descartar as observações ainda não registradas?")) return;
    setSelectedProvider(item.provider);
    setNotes(item.notes ?? "");
    setMessage(null);
  }

  async function registerSetup() {
    if (!selected || !token || !canManage) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await request<IntegrationSetupSummary>(
        "/integrations/setup",
        {
          method: "POST",
          body: JSON.stringify({
            provider: selected.provider,
            notes: notes.trim() || null,
          }),
        },
        token,
      );
      setItems((current) => current.map((item) =>
        item.provider === updated.provider ? updated : item,
      ));
      setNotes(updated.notes ?? "");
      setMessage(`${updated.name} registrada para configuração.`);
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao registrar integração.");
      setMessageKind("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="settings-panel-card integration-settings-stack">
      <div className="settings-panel-header">
        <div>
          <h2>Integrações</h2>
          <p>Conecte CRMs, ERPs e catálogos imobiliários sem misturá-los aos canais de atendimento.</p>
        </div>
        <Badge variant="muted"><Cable size={13} /> CRMs e ferramentas</Badge>
      </div>

      <div className="settings-readonly-note">
        Nesta etapa você registra a integração desejada e os recursos necessários. Credenciais
        serão configuradas depois em um fluxo protegido e específico para cada fornecedor.
      </div>

      {loading ? <div className="empty-state" aria-live="polite"><Loader2 className="spin-icon" size={18} /> Carregando integrações...</div> : null}
      {!loading && items.length === 0 ? <div className="empty-state">Nenhuma integração disponível.</div> : null}

      {!loading && items.length ? (
        <div className="integration-option-grid">
          {items.map((item) => (
            <button
              aria-pressed={selectedProvider === item.provider}
              className={`integration-option-card${selectedProvider === item.provider ? " active" : ""}`}
              key={item.provider}
              onClick={() => selectIntegration(item)}
              type="button"
            >
              <div className="integration-option-top">
                <span className="settings-icon"><Database size={18} /></span>
                <Badge variant={statusVariant(item.status)}>{statusLabels[item.status]}</Badge>
              </div>
              <div>
                <strong>{item.name}</strong>
                <small>{item.category}</small>
              </div>
              <p>{item.target_resources.join(" · ")}</p>
            </button>
          ))}
        </div>
      ) : null}

      {selected ? (
        <section className="integration-requirements">
          <div className="section-inline-header">
            <div>
              <strong>Configurar {selected.name}</strong>
              <span>Itens que precisaremos validar durante a homologação.</span>
            </div>
            <Badge variant={statusVariant(selected.status)}>{statusLabels[selected.status]}</Badge>
          </div>
          <div className="integration-requirement-grid">
            {selected.required_items.map((item) => <span key={item}>{item}</span>)}
          </div>
          <label>
            Observações para a configuração
            <textarea
              disabled={!canManage}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Ex.: usamos este sistema como origem oficial da carteira e queremos sincronizar imóveis ativos."
              rows={4}
              value={notes}
            />
          </label>
          <div className="settings-actions">
            {message ? <span className={`settings-feedback ${messageKind}`} role={messageKind === "error" ? "alert" : "status"}>{message}</span> : null}
            {!canManage ? <span>Somente administradores e gestores podem solicitar configurações.</span> : null}
            <button disabled={!canManage || saving || (!dirty && selected.status === "awaiting_credentials")} onClick={() => void registerSetup()} type="button">
              {saving ? <><Loader2 className="spin-icon" size={15} /> Registrando...</> : selected.status === "awaiting_credentials" ? <><RefreshCw size={15} /> Atualizar solicitação</> : "Registrar integração"}
            </button>
          </div>
        </section>
      ) : null}
    </Card>
  );
}

const statusLabels: Record<IntegrationSetupSummary["status"], string> = {
  not_configured: "Disponível",
  awaiting_credentials: "Aguardando configuração",
  testing: "Em validação",
  connected: "Conectada",
  error: "Requer atenção",
};

function statusVariant(status: IntegrationSetupSummary["status"]) {
  if (status === "connected") return "success" as const;
  if (status === "error") return "danger" as const;
  if (status === "awaiting_credentials" || status === "testing") return "accent" as const;
  return "muted" as const;
}
