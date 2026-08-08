import { Bot } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { Tenant } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";
import { KnowledgeSettingsPanel } from "./KnowledgeSettingsPanel";

type AgentConfig = {
  name: string;
  status: "active" | "inactive";
  handoff_rules: string;
  restrictions: string;
  transfer_message: string;
  voice_tone: "professional" | "friendly" | "consultative" | "informal";
  emoji_usage: "none" | "low" | "moderate";
};

const defaultAgent: AgentConfig = {
  name: "Agente de Leads",
  status: "active",
  handoff_rules: "Lead pronto para visita, pedido de negociação, dúvida complexa ou baixa confiança da IA.",
  restrictions: "Não prometer disponibilidade, não negociar valores finais e não assumir compromisso em nome do corretor.",
  transfer_message: "Vou acionar um corretor da equipe para seguir com as melhores opções.",
  voice_tone: "friendly",
  emoji_usage: "low",
};

export function AgentsSettingsPanel({
  tenant,
  onTenantChange,
  onDirtyChange,
}: {
  tenant: Tenant | null;
  onTenantChange: (tenant: Tenant) => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { token } = useAuth();
  const claims = getTokenClaims(token);
  const [agent, setAgent] = useState(defaultAgent);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error">("success");
  const [initialAgent, setInitialAgent] = useState<AgentConfig | null>(null);
  const canManage = claims?.role === "admin";
  const dirty = initialAgent !== null && JSON.stringify(agent) !== JSON.stringify(initialAgent);

  useEffect(() => {
    const saved = tenant?.settings.agents as { leads?: Partial<AgentConfig> } | undefined;
    const legacyTone = tenant?.settings.profile?.voice_tone;
    const nextAgent: AgentConfig = {
      ...defaultAgent,
      ...(saved?.leads ?? {}),
      voice_tone: normalizeTone(saved?.leads?.voice_tone ?? legacyTone),
    };
    setAgent(nextAgent);
    setInitialAgent(nextAgent);
  }, [tenant]);

  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  function updateAgent(patch: Partial<AgentConfig>) {
    setAgent((current) => ({ ...current, ...patch }));
  }

  async function save() {
    if (!claims || !tenant) {
      setMessage("Empresa não identificada no acesso atual.");
      setMessageKind("error");
      return;
    }
    const validationError = validateAgent(agent);
    if (validationError) {
      setMessage(validationError);
      setMessageKind("error");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const updated = await request<Tenant>(
        `/tenants/${claims.tenantId}/settings/agents`,
        {
          method: "PATCH",
          body: JSON.stringify({
            agents: {
              leads: {
                ...agent,
                name: agent.name.trim(),
                handoff_rules: agent.handoff_rules.trim(),
                restrictions: agent.restrictions.trim(),
                transfer_message: agent.transfer_message.trim(),
              },
            },
          }),
        },
        token,
      );
      onTenantChange(updated);
      setMessage("Configuração da IA salva.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao salvar a configuração da IA.");
      setMessageKind("error");
    } finally {
      setSaving(false);
    }
  }

  return <div className="ai-settings-stack">
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Configuração da IA</h2>
          <p>Personalize a conversa, os limites do agente e a passagem para a equipe.</p>
        </div>
        <Badge variant={agent.status === "active" ? "success" : "muted"}>
          <Bot size={13} />
          {agent.status === "active" ? "Ativo" : "Inativo"}
        </Badge>
      </div>

      <fieldset className="settings-form-fieldset" disabled={!canManage}>
      <div className="form-grid">
        <label>
          Nome do agente
          <input value={agent.name} onChange={(event) => updateAgent({ name: event.target.value })} />
        </label>
        <label>
          Status
          <select value={agent.status} onChange={(event) => updateAgent({ status: event.target.value as AgentConfig["status"] })}>
            <option value="active">Ativo</option>
            <option value="inactive">Inativo</option>
          </select>
        </label>
      </div>

      <div className="settings-subsection">
        <div>
          <h3>Estilo da conversa</h3>
          <p>Essas escolhas orientam todas as respostas do agente.</p>
        </div>
        <div className="form-grid">
          <label>
            Tom de voz
            <select value={agent.voice_tone} onChange={(event) => updateAgent({ voice_tone: event.target.value as AgentConfig["voice_tone"] })}>
              <option value="professional">Profissional</option>
              <option value="friendly">Próximo e cordial</option>
              <option value="consultative">Consultivo</option>
              <option value="informal">Informal</option>
            </select>
          </label>
          <label>
            Quantidade de emojis
            <select value={agent.emoji_usage} onChange={(event) => updateAgent({ emoji_usage: event.target.value as AgentConfig["emoji_usage"] })}>
              <option value="none">Não usar</option>
              <option value="low">Poucos</option>
              <option value="moderate">Moderada</option>
            </select>
          </label>
        </div>
      </div>

      <div className="settings-subsection">
        <div>
          <h3>Limites e atendimento humano</h3>
          <p>Defina os casos em que a equipe deve assumir a conversa.</p>
        </div>
        <div className="form-grid">
          <label className="form-span-2">
            Quando acionar um atendente humano
            <textarea value={agent.handoff_rules} onChange={(event) => updateAgent({ handoff_rules: event.target.value })} />
          </label>
          <label className="form-span-2">
            O que não pode fazer
            <textarea value={agent.restrictions} onChange={(event) => updateAgent({ restrictions: event.target.value })} />
          </label>
          <label className="form-span-2">
            Mensagem ao transferir para a equipe
            <input value={agent.transfer_message} onChange={(event) => updateAgent({ transfer_message: event.target.value })} />
          </label>
        </div>
      </div>
      </fieldset>

      <div className="settings-actions">
        {message ? <span className={`settings-feedback ${messageKind}`} role={messageKind === "error" ? "alert" : "status"} aria-live="polite">{message}</span> : null}
        {dirty ? <span className="unsaved-indicator">Alterações não salvas</span> : null}
        <button disabled={saving || !tenant || !canManage || !dirty} onClick={save} type="button">{saving ? "Salvando..." : "Salvar configuração da IA"}</button>
      </div>
    </Card>

    <KnowledgeSettingsPanel canManage={canManage} />
  </div>;
}

function validateAgent(agent: AgentConfig): string | null {
  if (agent.name.trim().length < 2) return "Informe um nome para o agente.";
  if (agent.handoff_rules.trim().length < 2) return "Informe quando acionar um atendente humano.";
  if (agent.restrictions.trim().length < 2) return "Informe o que o agente não pode fazer.";
  if (agent.transfer_message.trim().length < 2) return "Informe a mensagem de transferência.";
  return null;
}

function normalizeTone(value: unknown): AgentConfig["voice_tone"] {
  if (value === "professional" || value === "friendly" || value === "consultative" || value === "informal") return value;
  const text = String(value ?? "").toLowerCase();
  if (text.includes("informal")) return "informal";
  if (text.includes("consult")) return "consultative";
  if (text.includes("profissional") || text.includes("formal")) return "professional";
  return "friendly";
}
