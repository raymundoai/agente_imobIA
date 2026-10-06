import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Bot,
  Building2,
  Cable,
  Coins,
  Home,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Plus,
  ShieldCheck,
  Users,
} from "lucide-react";
import { request } from "../api/client";
import { AuthLayout } from "../components/AuthLayout";
import { Card } from "../components/Card";
import { MetricCard } from "../components/MetricCard";
import { runWithLoading } from "../lib/asyncState";
import { AgentPromptSettings, TenantAgentInstructions } from "./AgentPromptSettings";
import { BetaPricesSettings } from "./BetaPricesSettings";
import { FeedbackInbox } from "./FeedbackInbox";
import { TenantAccess } from "./TenantAccess";
import { BrandMark } from "../components/BrandMark";

type Dashboard = {
  total_clients: number;
  active_clients: number;
  inactive_clients: number;
  total_users: number;
  conversations: number;
  leads: number;
  properties: number;
  contacts: number;
  ai_calls: number;
  estimated_ai_cost: string;
  credits_outstanding: number;
};
type Tenant = {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  users: number;
  conversations: number;
  leads: number;
  properties: number;
  contacts: number;
  ai_calls: number;
  estimated_ai_cost: string;
  credit_balance: number;
  credit_enforcement: "meter_only" | "enforce";
  unlimited_messages: boolean;
  commercial_plan: string;
  commercial_status: "pilot" | "trial" | "pending" | "active" | "past_due" | "cancelled";
  beta_pricing: boolean;
  internal_test: boolean;
  commercial_enforcement: "meter_only" | "enforce";
  commercial_cycle_ends_at: string;
  commercial_available: Record<string, number>;
  credit_reserved: number;
  credit_available: number;
  integrations: Record<string, string>;
};
type CommercialPlan = {
  code: string;
  name: string;
  version: number;
  monthly_price_cents: number;
  currency: string;
  ai_attendances: number;
  property_searches: number;
  image_optimizations: number;
  max_users: number;
  is_public: boolean;
};
type CommercialPack = {
  code: string;
  name: string;
  resource: string;
  units: number;
  price_cents: number | null;
  currency: string;
  active: boolean;
};
type AsaasStatus = {
  configured: boolean;
  environment_url: string | null;
  account_id: string | null;
  account_name: string | null;
  webhook_url: string | null;
  webhook_notification_email: string | null;
  expected_webhook_url: string | null;
};
type AsaasSubscription = {
  id: string;
  provider_subscription_id: string | null;
  plan_code: string;
  value_cents: number;
  next_due_date: string;
  status: string;
  invoice_url: string | null;
  last_error: string | null;
  created_at: string;
};
const openAsaasStatuses = ["creating", "pending_payment", "active", "past_due"];
const asaasStatusLabels: Record<string, string> = {
  creating: "Criação não confirmada",
  pending_payment: "Aguardando pagamento",
  active: "Ativa",
  past_due: "Em atraso",
  cancelled: "Cancelada",
  failed: "Recusada pelo Asaas",
};
type TenantForm = {
  name: string;
  slug: string;
  admin_name: string;
  admin_email: string;
  admin_password: string;
};
const emptyTenant: TenantForm = {
  name: "",
  slug: "",
  admin_name: "",
  admin_email: "",
  admin_password: "",
};
const storageKey = "immobia.platform.auth.v1";
const platformTabs = [
  { key: "overview", label: "Visão geral", icon: LayoutDashboard },
  { key: "clients", label: "Clientes", icon: Building2 },
  { key: "agent", label: "Agente de IA", icon: Bot },
  { key: "feedback", label: "Feedback", icon: MessageSquare },
  { key: "settings", label: "Configurações", icon: Cable },
] as const;
type PlatformTab = (typeof platformTabs)[number]["key"];

function platformTabFromUrl(): PlatformTab {
  const requested = new URLSearchParams(window.location.search).get("aba");
  return platformTabs.some((tab) => tab.key === requested) ? (requested as PlatformTab) : "overview";
}

export function PlatformApp() {
  const [token, setToken] = useState(() =>
    window.localStorage.getItem(storageKey),
  );
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [plans, setPlans] = useState<CommercialPlan[]>([]);
  const [packs, setPacks] = useState<CommercialPack[]>([]);
  const [selected, setSelected] = useState<Tenant | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<TenantForm>(emptyTenant);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<PlatformTab>(() => platformTabFromUrl());

  useEffect(() => {
    const sync = () => setActiveTab(platformTabFromUrl());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  function selectTab(tab: PlatformTab) {
    if (tab === activeTab) return;
    const url = new URL(window.location.href);
    url.searchParams.set("aba", tab);
    window.history.pushState({}, "", `${url.pathname}${url.search}`);
    setActiveTab(tab);
  }

  async function load(activeToken = token) {
    if (!activeToken) {
      setLoading(false);
      return;
    }
    await runWithLoading(
      setLoading,
      async () => {
        const [stats, clients, planCatalog, packCatalog] = await Promise.all([
          request<Dashboard>("/platform/dashboard", {}, activeToken),
          request<Tenant[]>("/platform/tenants", {}, activeToken),
          request<CommercialPlan[]>("/platform/commercial/plans", {}, activeToken),
          request<CommercialPack[]>("/platform/commercial/packs", {}, activeToken),
        ]);
        setDashboard(stats);
        setTenants(clients);
        setPlans(planCatalog);
        setPacks(packCatalog);
        setSelected((current) =>
          current ? clients.find((item) => item.id === current.id) ?? null : null,
        );
        setError(null);
      },
      (reason) => setError(readError(reason)),
    );
  }
  useEffect(() => {
    void load();
  }, [token]);

  if (!token)
    return (
      <PlatformLogin
        onAuthenticated={(next) => {
          window.localStorage.setItem(storageKey, next);
          setToken(next);
        }}
      />
    );

  async function createTenant(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const created = await request<Tenant>(
        "/platform/tenants",
        { method: "POST", body: JSON.stringify(form) },
        token,
      );
      setForm(emptyTenant);
      setCreating(false);
      setSelected(created);
      await load();
    } catch (reason) {
      setError(readError(reason));
    }
  }
  async function toggleStatus(tenant: Tenant) {
    if (!window.confirm(tenant.status === "active" ? "Suspender este cliente e interromper seu acesso?" : "Reativar o acesso deste cliente?")) return;
    try {
      const updated = await request<Tenant>(
        `/platform/tenants/${tenant.id}/status`,
        {
          method: "PATCH",
          body: JSON.stringify({
            status: tenant.status === "active" ? "inactive" : "active",
          }),
        },
        token,
      );
      setSelected(updated);
      await load();
    } catch (reason) {
      setError(readError(reason));
    }
  }

  return (
    <main className="platform-page page-stack">
      <header className="platform-topbar">
        <div className="auth-brand-mark platform-brand">
          <span className="brand-icon"><BrandMark /></span>
          <strong>ImmobIA</strong>
          <span>Administração</span>
        </div>
        <button
          className="button-outline"
          onClick={() => {
            window.localStorage.removeItem(storageKey);
            setToken(null);
          }}
          type="button"
        >
          <LogOut size={16} />
          Sair
        </button>
      </header>
      <nav className="platform-tabs" aria-label="Seções da administração">
        {platformTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              aria-current={activeTab === tab.key ? "page" : undefined}
              className={activeTab === tab.key ? "platform-tab active" : "platform-tab"}
              key={tab.key}
              onClick={() => selectTab(tab.key)}
              type="button"
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </nav>
      {error ? <div className="error-box">{error}</div> : null}
      {loading ? <div className="empty-state large" aria-live="polite">Carregando administração da plataforma...</div> : null}
      {!loading && activeTab === "overview" ? (
      <section className="platform-metrics">
        <MetricCard
          icon={Building2}
          label="Clientes ativos"
          value={dashboard?.active_clients ?? 0}
          detail={`${dashboard?.inactive_clients ?? 0} inativos`}
        />
        <MetricCard
          icon={Users}
          label="Usuários"
          value={dashboard?.total_users ?? 0}
          detail="Em todas as imobiliárias"
        />
        <MetricCard
          icon={MessageSquare}
          label="Conversas"
          value={dashboard?.conversations ?? 0}
          detail={`${dashboard?.leads ?? 0} leads`}
        />
        <MetricCard
          icon={Bot}
          label="Chamadas de IA"
          value={dashboard?.ai_calls ?? 0}
          detail={`Custo OpenAI: US$ ${dashboard?.estimated_ai_cost ?? "0"}`}
        />
        <MetricCard
          icon={Coins}
          label="Créditos em carteira"
          value={dashboard?.credits_outstanding ?? 0}
          detail="Saldo total dos clientes"
        />
        <MetricCard
          icon={Home}
          label="Imóveis"
          value={dashboard?.properties ?? 0}
          detail={`${dashboard?.contacts ?? 0} contatos cadastrados`}
        />
      </section>
      ) : null}
      {!loading && activeTab === "agent" && token ? <AgentPromptSettings token={token} /> : null}
      {!loading && activeTab === "feedback" && token ? <FeedbackInbox token={token} /> : null}
      {!loading && activeTab === "settings" ? (
        <section className="page-stack">
          <div>
            <h2>Integrações</h2>
            <p>Serviços externos usados por toda a plataforma.</p>
          </div>
          <AsaasSetup token={token} />
          <BetaPricesSettings token={token} />
        </section>
      ) : null}
      {!loading && activeTab === "clients" ? (
      <div className="platform-layout">
        <Card>
          <div className="section-inline-header">
            <div>
              <h2>Imobiliárias clientes</h2>
              <span>{dashboard?.total_clients ?? 0} cadastradas</span>
            </div>
            <button
              className="secondary-button"
              onClick={() => {
                setCreating(true);
                setSelected(null);
              }}
              type="button"
            >
              <Plus size={15} />
              Novo cliente
            </button>
          </div>
          <div className="contacts-list">
            {tenants.length === 0 ? <div className="empty-state">Nenhum cliente cadastrado.</div> : null}
            {tenants.map((tenant) => (
              <button
                className={
                  selected?.id === tenant.id
                    ? "contact-row active"
                    : "contact-row"
                }
                key={tenant.id}
                onClick={() => {
                  setCreating(false);
                  setSelected(tenant);
                }}
                type="button"
              >
                <span className="conversation-avatar">
                  <Building2 size={16} />
                </span>
                <span>
                  <strong>{tenant.name}</strong>
                  <small>
                    {tenant.slug} · {tenant.users} usuários
                  </small>
                </span>
                <i
                  className={
                    tenant.status === "active"
                      ? "status-dot active"
                      : "status-dot"
                  }
                />
              </button>
            ))}
          </div>
        </Card>
        <Card>
          {creating ? (
            <form className="page-stack" onSubmit={createTenant}>
              <div>
                <h2>Novo cliente</h2>
              </div>
              <div className="form-grid">
                <Field
                  label="Imobiliária"
                  value={form.name}
                  onChange={(name) => setForm({ ...form, name })}
                />
                <Field
                  label="Slug"
                  value={form.slug}
                  onChange={(slug) => setForm({ ...form, slug })}
                />
                <Field
                  label="Administrador"
                  value={form.admin_name}
                  onChange={(admin_name) => setForm({ ...form, admin_name })}
                />
                <Field
                  label="Email"
                  type="email"
                  value={form.admin_email}
                  onChange={(admin_email) => setForm({ ...form, admin_email })}
                />
                <Field
                  label="Senha inicial"
                  type="password"
                  value={form.admin_password}
                  onChange={(admin_password) =>
                    setForm({ ...form, admin_password })
                  }
                />
              </div>
              <button className="primary-button" type="submit">Criar imobiliária e administrador</button>
            </form>
          ) : selected ? (
            <TenantDetail
              tenant={selected}
              token={token}
              plans={plans}
              packs={packs}
              onChanged={() => void load()}
              onToggle={() => void toggleStatus(selected)}
            />
          ) : (
            <div className="empty-state large">
              <ShieldCheck size={28} />
              Selecione um cliente para ver os detalhes.
            </div>
          )}
        </Card>
      </div>
      ) : null}
    </main>
  );
}

function PlatformLogin({
  onAuthenticated,
}: {
  onAuthenticated: (token: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await request<{ access_token: string }>(
        "/platform/auth/login",
        { method: "POST", body: JSON.stringify({ email, password }) },
      );
      onAuthenticated(result.access_token);
    } catch (reason) {
      setError(readError(reason));
    }
  }
  return (
    <AuthLayout badge="Administração">
      <form className="login-card" onSubmit={submit}>
        <div>
          <h1>Entrar na administração</h1>
          <p>Acesso exclusivo da equipe ImmobIA.</p>
        </div>
        <label>
          Email
          <input
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            value={email}
          />
        </label>
        <label>
          Senha
          <input
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            value={password}
          />
        </label>
        {error ? <div className="error-box">{error}</div> : null}
        <button className="primary-button" type="submit">Entrar</button>
      </form>
    </AuthLayout>
  );
}

function AsaasSetup({ token }: { token: string }) {
  const [connection, setConnection] = useState<AsaasStatus | null>(null);
  const [notificationEmail, setNotificationEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<string | null>(null);

  async function loadStatus() {
    setLoading(true);
    try {
      const status = await request<AsaasStatus>("/platform/asaas/status", {}, token);
      setConnection(status);
      setNotificationEmail((current) => current || status.webhook_notification_email || "");
      setFeedback(null);
    } catch (reason) {
      setConnection(null);
      setFeedback(readError(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStatus();
  }, [token]);

  async function provisionWebhook(event: FormEvent) {
    event.preventDefault();
    setFeedback(null);
    try {
      const webhook = await request<{ url: string }>(
        "/platform/asaas/webhook",
        {
          method: "POST",
          body: JSON.stringify({ notification_email: notificationEmail }),
        },
        token,
      );
      setFeedback(`Webhook ativo em ${webhook.url}`);
      void loadStatus();
    } catch (reason) {
      setFeedback(readError(reason));
    }
  }

  const webhookOutdated = Boolean(
    connection?.webhook_url && connection.expected_webhook_url && connection.webhook_url !== connection.expected_webhook_url,
  );

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Asaas</h2>
          <p>Ambiente de Sandbox para homologar assinaturas e eventos de pagamento.</p>
        </div>
        <button className="button-outline" disabled={loading} onClick={() => void loadStatus()} type="button">
          {loading ? "Verificando..." : "Verificar conexão"}
        </button>
      </div>
      {connection?.configured ? (
        <div className="info-box">
          Conectado{connection.account_name ? ` à conta ${connection.account_name}` : ""} · {connection.environment_url}
        </div>
      ) : !loading ? (
        <div className="error-box">A chave do Asaas ainda não está disponível no backend.</div>
      ) : null}
      {connection?.configured ? (
        webhookOutdated ? (
          <div className="error-box">
            O webhook aponta para {connection.webhook_url}, mas o endereço público atual é {connection.expected_webhook_url}. Clique em “Configurar webhook” para atualizar.
          </div>
        ) : connection.webhook_url ? (
          <div className="info-box">Webhook configurado em {connection.webhook_url}</div>
        ) : (
          <div className="info-box">Webhook ainda não configurado.</div>
        )
      ) : null}
      <form className="form-grid" onSubmit={provisionWebhook}>
        <Field label="E-mail para avisos do webhook" type="email" value={notificationEmail} onChange={setNotificationEmail} />
        <button className="primary-button form-action" disabled={!connection?.configured} type="submit">Configurar webhook</button>
      </form>
      {feedback ? <p>{feedback}</p> : null}
    </Card>
  );
}

function TenantDetail({
  tenant,
  token,
  plans,
  packs,
  onToggle,
  onChanged,
}: {
  tenant: Tenant;
  token: string;
  plans: CommercialPlan[];
  packs: CommercialPack[];
  onToggle: () => void;
  onChanged: () => void;
}) {
  const [planCode, setPlanCode] = useState(tenant.commercial_plan);
  const [enforcement, setEnforcement] = useState(tenant.commercial_enforcement);
  const [resource, setResource] = useState("ai_attendance");
  const [units, setUnits] = useState("100");
  const [packCode, setPackCode] = useState(packs[0]?.code ?? "");
  const billablePlans = useMemo(
    () => plans.filter((plan) => plan.is_public && plan.monthly_price_cents > 0),
    [plans],
  );
  const [asaasPlanCode, setAsaasPlanCode] = useState(billablePlans[0]?.code ?? "");
  const [billingName, setBillingName] = useState(tenant.name);
  const [billingEmail, setBillingEmail] = useState("");
  const [billingDocument, setBillingDocument] = useState("");
  const [nextDueDate, setNextDueDate] = useState(() => nextBusinessDay());
  const [asaasSubscriptions, setAsaasSubscriptions] = useState<AsaasSubscription[]>([]);
  // Kept across retries so a lost response is reconciled instead of billed twice.
  const [asaasIdempotencyKey, setAsaasIdempotencyKey] = useState(() => crypto.randomUUID());
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    setPlanCode(tenant.commercial_plan);
    setEnforcement(tenant.commercial_enforcement);
    setBillingName(tenant.name);
    setAsaasPlanCode((current) =>
      billablePlans.some((plan) => plan.code === current)
        ? current
        : (billablePlans[0]?.code ?? ""),
    );
  }, [tenant.id, tenant.commercial_enforcement, tenant.commercial_plan, tenant.name, billablePlans]);

  useEffect(() => {
    void loadAsaasSubscriptions();
  }, [tenant.id]);

  async function loadAsaasSubscriptions() {
    try {
      setAsaasSubscriptions(
        await request<AsaasSubscription[]>(`/platform/tenants/${tenant.id}/asaas/subscriptions`, {}, token),
      );
    } catch (reason) {
      setFeedback(readError(reason));
    }
  }

  async function saveSubscription() {
    if (!window.confirm("Atualizar o plano e a política comercial deste cliente?")) return;
    setFeedback(null);
    try {
      await request(
        `/platform/tenants/${tenant.id}/commercial-subscription`,
        {
          method: "PUT",
          body: JSON.stringify({
            plan_code: planCode,
            enforcement_mode: enforcement,
          }),
        },
        token,
      );
      setFeedback("Plano comercial atualizado.");
      onChanged();
    } catch (reason) {
      setFeedback(readError(reason));
    }
  }

  async function toggleBeta(next: boolean) {
    setFeedback(null);
    try {
      await request(
        `/platform/tenants/${tenant.id}/beta`,
        { method: "PATCH", body: JSON.stringify({ beta_pricing: next }) },
        token,
      );
      setFeedback(next ? "Cliente marcado como beta tester." : "Condição beta removida.");
      onChanged();
    } catch (reason) {
      setFeedback(readError(reason));
    }
  }

  async function toggleInternalTest(next: boolean) {
    setFeedback(null);
    try {
      await request(
        `/platform/tenants/${tenant.id}/internal-test`,
        { method: "PATCH", body: JSON.stringify({ internal_test: next }) },
        token,
      );
      setFeedback(next ? "Conta marcada como interna de testes: uso ilimitado." : "Conta voltou a ser cliente comum.");
      onChanged();
    } catch (reason) {
      setFeedback(readError(reason));
    }
  }

  async function grantUnits(event: FormEvent) {
    event.preventDefault();
    if (!window.confirm(`Adicionar ${Number(units).toLocaleString("pt-BR")} unidades para ${tenant.name}?`)) return;
    setFeedback(null);
    try {
      await request(
        `/platform/tenants/${tenant.id}/commercial-grants`,
        {
          method: "POST",
          body: JSON.stringify({
            resource,
            quantity: Number(units),
            source: "manual",
            reference: "Ajuste administrativo",
            idempotency_key: crypto.randomUUID(),
          }),
        },
        token,
      );
      setFeedback("Franquia adicional concedida.");
      onChanged();
    } catch (reason) {
      setFeedback(readError(reason));
    }
  }

  async function grantPack() {
    if (!packCode || !window.confirm("Conceder este pacote ao cliente?")) return;
    setFeedback(null);
    try {
      await request(
        `/platform/tenants/${tenant.id}/commercial-packs`,
        {
          method: "POST",
          body: JSON.stringify({
            pack_code: packCode,
            idempotency_key: crypto.randomUUID(),
          }),
        },
        token,
      );
      setFeedback("Pacote concedido.");
      onChanged();
    } catch (reason) {
      setFeedback(readError(reason));
    }
  }

  async function createAsaasSubscription(event: FormEvent) {
    event.preventDefault();
    if (!asaasPlanCode) return;
    const plan = plans.find((item) => item.code === asaasPlanCode);
    if (!window.confirm(`Criar assinatura Sandbox de ${plan?.name ?? asaasPlanCode} para ${tenant.name}? A franquia só será ativada após o evento de pagamento.`)) return;
    setFeedback(null);
    try {
      await request<AsaasSubscription>(
        `/platform/tenants/${tenant.id}/asaas/subscriptions`,
        {
          method: "POST",
          body: JSON.stringify({
            plan_code: asaasPlanCode,
            billing_type: "PIX",
            next_due_date: nextDueDate,
            enforcement_mode: "enforce",
            idempotency_key: asaasIdempotencyKey,
            customer: {
              name: billingName,
              email: billingEmail,
              cpf_cnpj: billingDocument,
              notification_disabled: true,
            },
          }),
        },
        token,
      );
      setAsaasIdempotencyKey(crypto.randomUUID());
      setFeedback("Assinatura Sandbox criada. Aguarde o webhook de confirmação para ativar a franquia.");
      onChanged();
    } catch (reason) {
      setFeedback(readError(reason));
    } finally {
      void loadAsaasSubscriptions();
    }
  }

  async function changeAsaasSubscription(subscription: AsaasSubscription, action: "reconcile" | "cancel") {
    if (
      action === "cancel" &&
      !window.confirm(
        `Cancelar a assinatura de ${tenant.name} no Asaas? As cobranças futuras deixam de ser geradas e, se ela estiver ativa, a franquia do plano é encerrada agora.`,
      )
    )
      return;
    setFeedback(null);
    try {
      await request(
        `/platform/tenants/${tenant.id}/asaas/subscriptions/${subscription.id}/${action}`,
        { method: "POST" },
        token,
      );
      setFeedback(action === "cancel" ? "Assinatura cancelada." : "Assinatura reconciliada com o Asaas.");
      onChanged();
    } catch (reason) {
      setFeedback(readError(reason));
    } finally {
      void loadAsaasSubscriptions();
    }
  }

  const openAsaasSubscription = asaasSubscriptions.find((item) => openAsaasStatuses.includes(item.status));

  return (
    <div className="page-stack">
      <div>
        <span className="eyebrow">Cliente</span>
        <h2>{tenant.name}</h2>
        <p>
          {tenant.slug} · criado em{" "}
          {new Date(tenant.created_at).toLocaleDateString("pt-BR")}
        </p>
      </div>
      <div className="contact-info-grid">
        <div>
          <Users size={15} />
          <span>{tenant.users} usuários</span>
        </div>
        <div>
          <span>{tenant.contacts} contatos</span>
        </div>
        <div>
          <span>{tenant.properties} imóveis</span>
        </div>
        <div>
          <span>{tenant.conversations} conversas</span>
        </div>
        <div>
          <span>{tenant.leads} leads</span>
        </div>
        <div>
          <span>
            {tenant.ai_calls} chamadas IA · US$ {tenant.estimated_ai_cost}
          </span>
        </div>
      </div>
      <div className="settings-subsection">
        <h3>Plano e franquias comerciais</h3>
        <label className="beta-toggle">
          <input checked={tenant.beta_pricing} onChange={(event) => void toggleBeta(event.target.checked)} type="checkbox" />
          <span>
            <strong>Beta tester</strong>
            <small>Vê e paga os preços beta (Configurações → Preços beta). Vale a partir da próxima assinatura.</small>
          </span>
        </label>
        <label className="beta-toggle">
          <input checked={tenant.internal_test} onChange={(event) => void toggleInternalTest(event.target.checked)} type="checkbox" />
          <span>
            <strong>Conta interna de testes</strong>
            <small>Uso ilimitado (medido, nunca bloqueado). No lugar dos planos, a conta vê só a contratação de teste de R$ 5,00, para validar o pagamento.</small>
          </span>
        </label>
        <div className="contact-info-grid">
          <div>
            <Coins size={15} />
            <span>Plano {planName(plans, tenant.commercial_plan)}</span>
          </div>
          <div>
            <span>{tenant.commercial_enforcement === "enforce" ? "Bloqueio por franquia" : "Piloto sem bloqueio"}</span>
          </div>
          <div>
            <span>{formatCommercialAvailable(tenant.commercial_available, "ai_attendance")} atendimentos IA</span>
          </div>
          <div>
            <span>{formatCommercialAvailable(tenant.commercial_available, "property_search_standard")} buscas</span>
          </div>
          <div>
            <span>{formatCommercialAvailable(tenant.commercial_available, "image_optimization")} otimizações</span>
          </div>
          <div>
            <span>Ciclo até {new Date(tenant.commercial_cycle_ends_at).toLocaleDateString("pt-BR")}</span>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Plano
            <select value={planCode} onChange={(event) => setPlanCode(event.target.value)}>
              {plans
                .filter((plan) => plan.code !== "teste_gratis" || plan.code === tenant.commercial_plan)
                .map((plan) => <option key={`${plan.code}:${plan.version}`} value={plan.code}>{plan.name} · {formatBrl(plan.monthly_price_cents)}</option>)}
            </select>
          </label>
          <label>
            Política
            <select value={enforcement} onChange={(event) => setEnforcement(event.target.value as "meter_only" | "enforce")}>
              <option value="meter_only">Somente medir (piloto)</option>
              <option value="enforce">Aplicar franquias</option>
            </select>
          </label>
          <button className="primary-button form-action" onClick={() => void saveSubscription()} type="button">Salvar plano</button>
        </div>

        <form className="form-grid" onSubmit={grantUnits}>
          <label>
            Recurso adicional
            <select value={resource} onChange={(event) => setResource(event.target.value)}>
              <option value="ai_attendance">Atendimentos da IA</option>
              <option value="property_search_standard">Buscas de imóveis</option>
              <option value="image_optimization">Otimizações de fotos</option>
            </select>
          </label>
          <Field label="Unidades" type="number" value={units} onChange={setUnits} />
          <button className="primary-button form-action" type="submit">Conceder franquia</button>
        </form>

        <div className="form-grid">
          <label>
            Pacote preparado para o gateway
            <select value={packCode} onChange={(event) => setPackCode(event.target.value)}>
              {packs.map((pack) => <option key={pack.code} value={pack.code}>{pack.name}</option>)}
            </select>
          </label>
          <button className="button-outline form-action" disabled={!packCode} onClick={() => void grantPack()} type="button">
            Conceder pacote manualmente
          </button>
        </div>
        {feedback ? <p>{feedback}</p> : null}
      </div>
      <div className="settings-subsection">
        <h3>Assinatura Asaas (Sandbox)</h3>
        <p>Crie uma cobrança recorrente de teste. O plano só é ativado quando o Asaas confirmar o pagamento pelo webhook.</p>
        {asaasSubscriptions.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Plano</th>
                  <th>Situação</th>
                  <th>Valor</th>
                  <th>Criada em</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {asaasSubscriptions.map((subscription) => (
                  <tr key={subscription.id}>
                    <td>{planName(plans, subscription.plan_code)}</td>
                    <td>
                      {asaasStatusLabels[subscription.status] ?? subscription.status}
                      {subscription.last_error ? <small> · {subscription.last_error}</small> : null}
                    </td>
                    <td>{formatBrl(subscription.value_cents)}/mês</td>
                    <td>{new Date(subscription.created_at).toLocaleDateString("pt-BR")}</td>
                    <td className="table-actions">
                      {subscription.invoice_url && openAsaasStatuses.includes(subscription.status) ? (
                        <a href={subscription.invoice_url} rel="noreferrer" target="_blank">Cobrança</a>
                      ) : null}
                      {subscription.status === "creating" ? (
                        <button className="button-outline" onClick={() => void changeAsaasSubscription(subscription, "reconcile")} type="button">
                          Reconciliar
                        </button>
                      ) : null}
                      {openAsaasStatuses.includes(subscription.status) ? (
                        <button className="button-outline" onClick={() => void changeAsaasSubscription(subscription, "cancel")} type="button">
                          Cancelar
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {openAsaasSubscription ? (
          <div className="info-box">
            Este cliente já tem uma assinatura em aberto. Cancele-a antes de criar outra, para não cobrar em dobro.
          </div>
        ) : null}
        <form className="form-grid" onSubmit={createAsaasSubscription}>
          <label>
            Plano cobrado
            <select value={asaasPlanCode} onChange={(event) => setAsaasPlanCode(event.target.value)}>
              {billablePlans.map((plan) => <option key={plan.code} value={plan.code}>{plan.name} · {formatBrl(plan.monthly_price_cents)}/mês</option>)}
            </select>
          </label>
          <Field label="Razão social ou nome" value={billingName} onChange={setBillingName} />
          <Field label="E-mail financeiro" type="email" value={billingEmail} onChange={setBillingEmail} />
          <Field label="CPF ou CNPJ" value={billingDocument} onChange={setBillingDocument} />
          <Field label="Primeiro vencimento" type="date" value={nextDueDate} onChange={setNextDueDate} />
          <button className="primary-button form-action" disabled={!asaasPlanCode || Boolean(openAsaasSubscription)} type="submit">Criar assinatura PIX</button>
        </form>
      </div>
      <TenantAccess tenantId={tenant.id} token={token} />
      <TenantAgentInstructions tenantId={tenant.id} token={token} />
      <div className="settings-subsection">
        <h3>Telemetria técnica interna</h3>
        <p>
          US$ {tenant.estimated_ai_cost} de custo OpenAI registrado · {tenant.credit_balance.toLocaleString("pt-BR")} créditos técnicos · {tenant.credit_reserved.toLocaleString("pt-BR")} reservados.
        </p>
      </div>
      <div>
        <h3>Integrações</h3>
        <p>
          {Object.entries(tenant.integrations)
            .map(([name, status]) => `${name}: ${status}`)
            .join(" · ") || "Nenhuma integração configurada"}
        </p>
      </div>
      <button
        className={tenant.status === "active" ? "primary-button button-danger tenant-status-action" : "primary-button tenant-status-action"}
        onClick={onToggle}
        type="button"
      >
        {tenant.status === "active" ? "Suspender cliente" : "Reativar cliente"}
      </button>
    </div>
  );
}
function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label>
      {label}
      <input
        onChange={(e) => onChange(e.target.value)}
        required
        type={type}
        value={value}
      />
    </label>
  );
}
function readError(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Falha na administração da plataforma.";
}

function planName(plans: CommercialPlan[], code: string) {
  return plans.find((plan) => plan.code === code)?.name ?? code;
}

function formatCommercialAvailable(values: Record<string, number>, resource: string) {
  return (values[resource] ?? 0).toLocaleString("pt-BR");
}

function formatBrl(cents: number) {
  return new Intl.NumberFormat("pt-BR", {
    currency: "BRL",
    style: "currency",
  }).format(cents / 100);
}

function nextBusinessDay() {
  const date = new Date();
  date.setHours(12, 0, 0, 0);
  date.setDate(date.getDate() + 1);
  while (date.getDay() === 0 || date.getDay() === 6) date.setDate(date.getDate() + 1);
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("-");
}
