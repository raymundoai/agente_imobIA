import {
  Building2,
  CalendarDays,
  DatabaseZap,
  FileSpreadsheet,
  Mail,
  MessageCircle,
  Plus,
  Search,
  ShieldCheck,
  Timer,
  X,
} from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { IntegrationSetupSummary, Tenant } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";

type IntegrationCategory = "Atendimento" | "CRM" | "Google" | "Gestão" | "Captação";

type IntegrationOption = {
  category: IntegrationCategory;
  description: string;
  icon: ReactNode;
  name: string;
  provider?: string;
  status: "focus" | "soon";
};

const integrationOptions: IntegrationOption[] = [
  {
    category: "Gestão",
    description: "Sincronização de carteira, contatos, proprietários e rotinas operacionais.",
    icon: <ShieldCheck size={20} />,
    name: "Kenlo",
    provider: "kenlo",
    status: "focus",
  },
  {
    category: "Gestão",
    description: "Integração com imóveis, leads e dados comerciais da operação imobiliária.",
    icon: <Building2 size={20} />,
    name: "Tecimob",
    provider: "tecimob",
    status: "focus",
  },
  {
    category: "Gestão",
    description: "Conexão com carteira de imóveis, CRM e fluxos de atendimento.",
    icon: <Building2 size={20} />,
    name: "Jetimob",
    provider: "jetimob",
    status: "focus",
  },
  {
    category: "Captação",
    description: "Base de empreendimentos e unidades para busca, recomendação e enriquecimento.",
    icon: <DatabaseZap size={20} />,
    name: "Órulo",
    provider: "orulo",
    status: "focus",
  },
  {
    category: "Atendimento",
    description: "Conexão alternativa para desenvolvimento e testes controlados.",
    icon: <MessageCircle size={20} />,
    name: "WhatsApp Evolution",
    status: "soon",
  },
  {
    category: "Atendimento",
    description: "Mensagens do Instagram para atendimento de leads e clientes.",
    icon: <MessageCircle size={20} />,
    name: "Instagram",
    status: "soon",
  },
  {
    category: "CRM",
    description: "Sincronização de contatos, oportunidades e etapas comerciais.",
    icon: <Building2 size={20} />,
    name: "HubSpot",
    status: "soon",
  },
  {
    category: "CRM",
    description: "Leads, funil comercial e atividades do time de vendas.",
    icon: <Building2 size={20} />,
    name: "Pipedrive",
    status: "soon",
  },
  {
    category: "CRM",
    description: "Integração com carteira, funil e gestão de relacionamento.",
    icon: <Building2 size={20} />,
    name: "Vista Software",
    status: "soon",
  },
  {
    category: "Google",
    description: "Importação e atualização de listas em planilhas compartilhadas.",
    icon: <FileSpreadsheet size={20} />,
    name: "Google Sheets",
    status: "soon",
  },
  {
    category: "Google",
    description: "Criação de eventos, visitas e lembretes para equipe e clientes.",
    icon: <CalendarDays size={20} />,
    name: "Google Agenda",
    status: "soon",
  },
  {
    category: "Google",
    description: "Envio e leitura assistida de e-mails operacionais.",
    icon: <Mail size={20} />,
    name: "Gmail",
    status: "soon",
  },
  {
    category: "Gestão",
    description: "Conexão financeira e operacional conforme necessidade do cliente.",
    icon: <ShieldCheck size={20} />,
    name: "Superlógica",
    status: "soon",
  },
  {
    category: "Captação",
    description: "Integração com fontes e carteiras externas de imóveis.",
    icon: <DatabaseZap size={20} />,
    name: "DWV",
    status: "soon",
  },
];

const categoryLabels: IntegrationCategory[] = ["Atendimento", "CRM", "Google", "Gestão", "Captação"];

export function IntegrationsSettingsPanel({
  tenant,
}: {
  tenant: Tenant | null;
  onTenantChange: (tenant: Tenant) => void;
}) {
  const { token } = useAuth();
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<IntegrationCategory | "Todas">("Todas");
  const [selectedIntegration, setSelectedIntegration] = useState<string | null>(null);
  const [setupItems, setSetupItems] = useState<IntegrationSetupSummary[]>([]);
  const [savingSetup, setSavingSetup] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    request<IntegrationSetupSummary[]>("/integrations/setup", {}, token)
      .then(setSetupItems)
      .catch(() => setSetupItems([]));
  }, [token]);

  const filteredOptions = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return integrationOptions.filter((option) => {
      const matchesCategory = selectedCategory === "Todas" || option.category === selectedCategory;
      const matchesQuery =
        !normalized ||
        [option.name, option.description, option.category].some((value) =>
          value.toLowerCase().includes(normalized),
        );
      return matchesCategory && matchesQuery;
    });
  }, [query, selectedCategory]);

  const selectedOption = integrationOptions.find((option) => option.name === selectedIntegration);
  const selectedSetup = selectedOption?.provider
    ? setupItems.find((item) => item.provider === selectedOption.provider)
    : null;

  async function markForSetup() {
    if (!selectedOption?.provider) {
      return;
    }
    setSavingSetup(true);
    setMessage(null);
    try {
      const updated = await request<IntegrationSetupSummary>(
        "/integrations/setup",
        {
          method: "POST",
          body: JSON.stringify({
            provider: selectedOption.provider,
            notes: `Setup solicitado para ${tenant?.name ?? "empresa atual"}.`,
          }),
        },
        token,
      );
      setSetupItems((current) =>
        current.some((item) => item.provider === updated.provider)
          ? current.map((item) => (item.provider === updated.provider ? updated : item))
          : [...current, updated],
      );
      setMessage(`${updated.name} marcado como aguardando credenciais.`);
      setCatalogOpen(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao marcar integração.");
    } finally {
      setSavingSetup(false);
    }
  }

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header compact">
        <div>
          <h2>Integrações</h2>
          <p>Conecte sistemas externos usados no atendimento, operação e captação.</p>
        </div>
        <Badge variant="accent">
          <ShieldCheck size={13} />
          setup assistido
        </Badge>
      </div>

      <button className="add-integration-card" onClick={() => setCatalogOpen(true)} type="button">
        <span className="settings-icon">
          <Plus size={20} />
        </span>
        <div>
          <strong>Adicionar Integração</strong>
          <small>
            No MVP, o setup será priorizado para Kenlo, Tecimob, Jetimob e Órulo.
          </small>
        </div>
      </button>

      <div className="settings-summary-grid">
        <div className="settings-summary">
          <span>Empresa</span>
          <strong>{tenant?.name ?? "Não carregada"}</strong>
        </div>
        <div className="settings-summary">
          <span>Prioridade</span>
          <strong>4 integrações</strong>
        </div>
      </div>
      <div className="integration-setup-list">
        {integrationOptions
          .filter((option) => option.status === "focus" && option.provider)
          .map((option) => {
            const setup = setupItems.find((item) => item.provider === option.provider);
            return (
              <div className="integration-setup-row" key={option.name}>
                <span className="settings-icon">{option.icon}</span>
                <div>
                  <strong>{option.name}</strong>
                  <small>{setupStatusLabels[setup?.status ?? "not_configured"]}</small>
                </div>
                <Badge variant={setup?.status === "connected" ? "success" : "muted"}>
                  {setup?.status === "connected" ? "Conectado" : "Setup"}
                </Badge>
              </div>
            );
          })}
      </div>
      {message ? <div className="settings-status">{message}</div> : null}

      {catalogOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section aria-modal="true" className="demand-modal integrations-catalog-modal" role="dialog">
            <div className="modal-header">
              <div>
                <h2>Adicionar integração</h2>
                <p>Escolha uma integração prioritária para mapear no setup do cliente.</p>
              </div>
              <button className="icon-button" onClick={() => setCatalogOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            <div className="integration-catalog-toolbar">
              <label className="catalog-search">
                <Search size={16} />
                <input
                  aria-label="Buscar integração"
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Buscar por sistema ou categoria"
                  value={query}
                />
              </label>
              <div className="catalog-categories">
                {["Todas", ...categoryLabels].map((category) => (
                  <button
                    className={selectedCategory === category ? "filter-chip active" : "filter-chip"}
                    key={category}
                    onClick={() => setSelectedCategory(category as IntegrationCategory | "Todas")}
                    type="button"
                  >
                    {category}
                  </button>
                ))}
              </div>
            </div>

            <div className="integration-option-grid">
              {filteredOptions.map((option) => (
                <button
                  className={
                    selectedIntegration === option.name
                      ? "integration-option-card active"
                      : "integration-option-card"
                  }
                  disabled={option.status === "soon"}
                  key={option.name}
                  onClick={() => {
                    if (option.status === "focus") {
                      setSelectedIntegration(option.name);
                    }
                  }}
                  type="button"
                >
                  <div className="integration-option-top">
                    <span className="settings-icon">{option.icon}</span>
                    <Badge variant={option.status === "focus" ? "accent" : "muted"}>
                      {option.status === "focus" ? (
                        <>
                          <ShieldCheck size={12} />
                          foco MVP
                        </>
                      ) : (
                        <>
                          <Timer size={12} />
                          Em breve
                        </>
                      )}
                    </Badge>
                  </div>
                  <strong>{option.name}</strong>
                  <small>{option.category}</small>
                  <p>{option.description}</p>
                </button>
              ))}
            </div>

            {selectedSetup ? (
              <div className="integration-requirements">
                <strong>Informações necessárias para {selectedSetup.name}</strong>
                <div className="integration-requirement-grid">
                  {selectedSetup.required_items.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="modal-actions">
              <span>
                {selectedIntegration
                  ? `${selectedIntegration} selecionado para setup.`
                  : "Selecione uma integração para registrar a intenção."}
              </span>
              <button className="button-outline" onClick={() => setCatalogOpen(false)} type="button">
                Fechar
              </button>
              <button disabled={!selectedIntegration || savingSetup} onClick={markForSetup} type="button">
                {savingSetup ? "Marcando..." : "Marcar para setup"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </Card>
  );
}

const setupStatusLabels: Record<IntegrationSetupSummary["status"], string> = {
  not_configured: "Não configurado",
  awaiting_credentials: "Aguardando credenciais",
  testing: "Em teste",
  connected: "Conectado",
  error: "Erro de conexão",
};
