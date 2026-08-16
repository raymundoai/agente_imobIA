import { FormEvent, useEffect, useState } from "react";
import {
  Bot,
  Building2,
  Coins,
  LogOut,
  MessageSquare,
  Plus,
  ShieldCheck,
  Users,
} from "lucide-react";
import { request } from "../api/client";
import { Card } from "../components/Card";
import { MetricCard } from "../components/MetricCard";
import { runWithLoading } from "../lib/asyncState";

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
  commercial_status: "pilot" | "active" | "past_due" | "cancelled";
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
const storageKey = "imobia.platform.auth.v1";

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
      <header className="page-header platform-header">
        <div>
          <span className="eyebrow">ImobIA Platform</span>
          <h1>Administração da plataforma</h1>
          <p>
            Clientes, operação, integrações e consumo em um ambiente separado.
          </p>
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
      {error ? <div className="error-box">{error}</div> : null}
      {loading ? <div className="empty-state large" aria-live="polite">Carregando administração da plataforma...</div> : null}
      {!loading ? <>
      <section className="metrics-grid">
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
      </section>
      <div className="platform-layout">
        <Card>
          <div className="section-inline-header">
            <div>
              <h2>Imobiliárias clientes</h2>
              <span>{dashboard?.total_clients ?? 0} cadastradas</span>
            </div>
            <button
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
                <span className="eyebrow">Onboarding</span>
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
              <button type="submit">Criar imobiliária e administrador</button>
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
      </> : null}
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
    <main className="login-page">
      <div className="login-heading">
        <ShieldCheck size={36} />
        <h1>ImobIA Platform</h1>
        <p>Acesso exclusivo da administração</p>
      </div>
      <form className="login-card" onSubmit={submit}>
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
        <button type="submit">Entrar</button>
      </form>
    </main>
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
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    setPlanCode(tenant.commercial_plan);
    setEnforcement(tenant.commercial_enforcement);
  }, [tenant.id, tenant.commercial_enforcement, tenant.commercial_plan]);

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
              {plans.map((plan) => <option key={`${plan.code}:${plan.version}`} value={plan.code}>{plan.name} · {formatBrl(plan.monthly_price_cents)}</option>)}
            </select>
          </label>
          <label>
            Política
            <select value={enforcement} onChange={(event) => setEnforcement(event.target.value as "meter_only" | "enforce")}>
              <option value="meter_only">Somente medir (piloto)</option>
              <option value="enforce">Aplicar franquias</option>
            </select>
          </label>
          <button onClick={() => void saveSubscription()} type="button">Salvar plano</button>
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
          <button type="submit">Conceder franquia</button>
        </form>

        <div className="form-grid">
          <label>
            Pacote preparado para o gateway
            <select value={packCode} onChange={(event) => setPackCode(event.target.value)}>
              {packs.map((pack) => <option key={pack.code} value={pack.code}>{pack.name}</option>)}
            </select>
          </label>
          <button className="button-outline" disabled={!packCode} onClick={() => void grantPack()} type="button">
            Conceder pacote manualmente
          </button>
        </div>
        {feedback ? <p>{feedback}</p> : null}
      </div>
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
        className={tenant.status === "active" ? "button-danger" : ""}
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
