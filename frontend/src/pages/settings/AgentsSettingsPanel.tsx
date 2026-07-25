import { Bot } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { Tenant, TenantSettings } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";

type AgentConfig = {
  name: string;
  status: "active" | "inactive";
  audience: string;
  goal: string;
  channels: string;
  handoff_rules: string;
  restrictions: string;
  transfer_message: string;
  knowledge_scope: string;
};

const defaultAgent: AgentConfig = {
  name: "Agente de Leads",
  status: "active",
  audience: "Novos contatos, compradores e interessados em locação",
  goal: "Receber o lead, entender o perfil do imóvel, cadastrar a demanda e acionar o corretor quando estiver qualificado.",
  channels: "WhatsApp, Telegram",
  handoff_rules: "Lead pronto para visita, pedido de negociação, dúvida complexa ou baixa confiança da IA.",
  restrictions: "Não prometer disponibilidade, não negociar valores finais e não assumir compromisso em nome do corretor.",
  transfer_message: "Vou acionar um corretor da equipe para seguir com as melhores opções.",
  knowledge_scope: "Regiões atendidas, tipos de imóvel, processo de compra e locação e critérios de qualificação.",
};

export function AgentsSettingsPanel({
  tenant,
  onTenantChange,
}: {
  tenant: Tenant | null;
  onTenantChange: (tenant: Tenant) => void;
}) {
  const { token } = useAuth();
  const claims = getTokenClaims(token);
  const [agent, setAgent] = useState(defaultAgent);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const saved = tenant?.settings.agents as { leads?: Partial<AgentConfig> } | undefined;
    setAgent({ ...defaultAgent, ...(saved?.leads ?? {}) });
  }, [tenant]);

  function updateAgent(patch: Partial<AgentConfig>) {
    setAgent((current) => ({ ...current, ...patch }));
  }

  async function save() {
    if (!claims || !tenant) {
      setMessage("Empresa não identificada no acesso atual.");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const settings: TenantSettings = {
        ...tenant.settings,
        agents: { leads: agent },
      };
      const updated = await request<Tenant>(
        `/tenants/${claims.tenantId}/settings`,
        { method: "PATCH", body: JSON.stringify({ settings }) },
        token,
      );
      onTenantChange(updated);
      setMessage("Agente salvo.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao salvar o agente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Agente de qualificação</h2>
          <p>Configure o atendimento inicial, os limites da IA e a passagem para a equipe.</p>
        </div>
        <Badge variant={agent.status === "active" ? "success" : "muted"}>
          <Bot size={13} />
          {agent.status === "active" ? "Ativo" : "Inativo"}
        </Badge>
      </div>

      <div className="settings-subsection">
        <div className="form-grid">
          <label>
            Nome do agente
            <input value={agent.name} onChange={(event) => updateAgent({ name: event.target.value })} />
          </label>
          <label>
            Status
            <select
              value={agent.status}
              onChange={(event) => updateAgent({ status: event.target.value as AgentConfig["status"] })}
            >
              <option value="active">Ativo</option>
              <option value="inactive">Inativo</option>
            </select>
          </label>
          <label className="form-span-2">
            Público atendido
            <input value={agent.audience} onChange={(event) => updateAgent({ audience: event.target.value })} />
          </label>
          <label className="form-span-2">
            Objetivo
            <textarea value={agent.goal} onChange={(event) => updateAgent({ goal: event.target.value })} />
          </label>
          <label>
            Canais onde atua
            <input value={agent.channels} onChange={(event) => updateAgent({ channels: event.target.value })} />
          </label>
          <label>
            Base usada
            <input value={agent.knowledge_scope} onChange={(event) => updateAgent({ knowledge_scope: event.target.value })} />
          </label>
          <label className="form-span-2">
            Quando chamar uma pessoa
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

      <div className="settings-actions">
        {message ? <span>{message}</span> : null}
        <button disabled={saving || !tenant} onClick={save} type="button">
          {saving ? "Salvando..." : "Salvar agente"}
        </button>
      </div>
    </Card>
  );
}
