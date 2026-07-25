import { Bot, Headphones, UserRoundSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { Tenant, TenantSettings } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";

type AgentKey = "leads" | "service";

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

const defaultAgents: Record<AgentKey, AgentConfig> = {
  leads: {
    name: "Agente de Leads",
    status: "active",
    audience: "Novos contatos, compradores e interessados em locação",
    goal: "Receber o lead, entender o perfil do imóvel, cadastrar demanda e acionar o corretor quando estiver qualificado.",
    channels: "WhatsApp, Instagram",
    handoff_rules: "Lead pronto para visita, pedido de negociação, dúvida complexa ou baixa confiança da IA.",
    restrictions: "Não prometer disponibilidade, não negociar valores finais e não assumir compromisso em nome do corretor.",
    transfer_message: "Vou acionar um corretor da equipe para seguir com as melhores opções.",
    knowledge_scope: "Regiões atendidas, tipos de imóvel, processo de compra e locação, critérios de qualificação.",
  },
  service: {
    name: "Agente de Atendimento",
    status: "active",
    audience: "Inquilinos e proprietários ativos",
    goal: "Resolver dúvidas operacionais, coletar informações, abrir chamados e encaminhar situações sensíveis para a equipe.",
    channels: "WhatsApp",
    handoff_rules: "Manutenção urgente, reclamação grave, inadimplência, rescisão, jurídico ou pedido de alteração contratual.",
    restrictions: "Não negociar dívida, não dar orientação jurídica conclusiva e não alterar contratos.",
    transfer_message: "Vou registrar sua solicitação e acionar a equipe responsável.",
    knowledge_scope: "FAQ de locação, manutenção, boletos, repasses, contratos e procedimentos internos.",
  },
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
  const [activeAgent, setActiveAgent] = useState<AgentKey>("leads");
  const [agents, setAgents] = useState<Record<AgentKey, AgentConfig>>(defaultAgents);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const savedAgents = tenant?.settings.agents as Partial<Record<AgentKey, Partial<AgentConfig>>> | undefined;
    setAgents({
      leads: { ...defaultAgents.leads, ...(savedAgents?.leads ?? {}) },
      service: { ...defaultAgents.service, ...(savedAgents?.service ?? {}) },
    });
  }, [tenant]);

  function updateAgent(patch: Partial<AgentConfig>) {
    setAgents((current) => ({
      ...current,
      [activeAgent]: { ...current[activeAgent], ...patch },
    }));
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
        agents,
      };
      const updated = await request<Tenant>(
        `/tenants/${claims.tenantId}/settings`,
        {
          method: "PATCH",
          body: JSON.stringify({ settings }),
        },
        token,
      );
      onTenantChange(updated);
      setMessage("Agentes salvos.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao salvar agentes.");
    } finally {
      setSaving(false);
    }
  }

  const current = agents[activeAgent];

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Agentes</h2>
          <p>Configure quem a IA atende, o que ela pode fazer e quando deve chamar a equipe.</p>
        </div>
        <Badge variant="success">
          <Bot size={13} />
          2 agentes
        </Badge>
      </div>

      <div className="agent-card-grid">
        <button
          className={activeAgent === "leads" ? "agent-choice active" : "agent-choice"}
          onClick={() => setActiveAgent("leads")}
          type="button"
        >
          <UserRoundSearch size={19} />
          <span>
            <strong>{agents.leads.name}</strong>
            <small>Novos leads e primeiros contatos</small>
          </span>
          <Badge variant={agents.leads.status === "active" ? "success" : "muted"}>
            {agents.leads.status === "active" ? "Ativo" : "Inativo"}
          </Badge>
        </button>
        <button
          className={activeAgent === "service" ? "agent-choice active" : "agent-choice"}
          onClick={() => setActiveAgent("service")}
          type="button"
        >
          <Headphones size={19} />
          <span>
            <strong>{agents.service.name}</strong>
            <small>Inquilinos e proprietários</small>
          </span>
          <Badge variant={agents.service.status === "active" ? "success" : "muted"}>
            {agents.service.status === "active" ? "Ativo" : "Inativo"}
          </Badge>
        </button>
      </div>

      <div className="settings-subsection">
        <h3>{current.name}</h3>
        <div className="form-grid">
          <label>
            Nome do agente
            <input value={current.name} onChange={(event) => updateAgent({ name: event.target.value })} />
          </label>
          <label>
            Status
            <select
              value={current.status}
              onChange={(event) => updateAgent({ status: event.target.value as AgentConfig["status"] })}
            >
              <option value="active">Ativo</option>
              <option value="inactive">Inativo</option>
            </select>
          </label>
          <label className="form-span-2">
            Público atendido
            <input
              value={current.audience}
              onChange={(event) => updateAgent({ audience: event.target.value })}
            />
          </label>
          <label className="form-span-2">
            Objetivo
            <textarea value={current.goal} onChange={(event) => updateAgent({ goal: event.target.value })} />
          </label>
          <label>
            Canais onde atua
            <input
              value={current.channels}
              onChange={(event) => updateAgent({ channels: event.target.value })}
            />
          </label>
          <label>
            Base usada
            <input
              value={current.knowledge_scope}
              onChange={(event) => updateAgent({ knowledge_scope: event.target.value })}
            />
          </label>
          <label className="form-span-2">
            Quando chamar uma pessoa
            <textarea
              value={current.handoff_rules}
              onChange={(event) => updateAgent({ handoff_rules: event.target.value })}
            />
          </label>
          <label className="form-span-2">
            O que não pode fazer
            <textarea
              value={current.restrictions}
              onChange={(event) => updateAgent({ restrictions: event.target.value })}
            />
          </label>
          <label className="form-span-2">
            Mensagem ao transferir para a equipe
            <input
              value={current.transfer_message}
              onChange={(event) => updateAgent({ transfer_message: event.target.value })}
            />
          </label>
        </div>
      </div>

      <div className="settings-actions">
        {message ? <span>{message}</span> : null}
        <button disabled={saving || !tenant} onClick={save} type="button">
          {saving ? "Salvando..." : "Salvar agentes"}
        </button>
      </div>
    </Card>
  );
}
