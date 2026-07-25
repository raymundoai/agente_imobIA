import { FormEvent, useEffect, useState } from "react";
import { Bot, Building2, LogOut, MessageSquare, Plus, ShieldCheck, Users } from "lucide-react";
import { request } from "../api/client";
import { Card } from "../components/Card";
import { MetricCard } from "../components/MetricCard";

type Dashboard = {
  total_clients:number; active_clients:number; inactive_clients:number; total_users:number;
  conversations:number; leads:number; properties:number; contacts:number; ai_calls:number;
  estimated_ai_cost:string;
};
type Tenant = {
  id:string; name:string; slug:string; status:string; created_at:string; users:number;
  conversations:number; leads:number; properties:number; contacts:number; ai_calls:number;
  estimated_ai_cost:string; integrations:Record<string,string>;
};
type TenantForm = {name:string; slug:string; admin_name:string; admin_email:string; admin_password:string};
const emptyTenant: TenantForm = {name:"",slug:"",admin_name:"",admin_email:"",admin_password:""};
const storageKey = "imobia.platform.auth.v1";

export function PlatformApp() {
  const [token, setToken] = useState(() => window.localStorage.getItem(storageKey));
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selected, setSelected] = useState<Tenant | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<TenantForm>(emptyTenant);
  const [error, setError] = useState<string | null>(null);

  async function load(activeToken = token) {
    if (!activeToken) return;
    const [stats, clients] = await Promise.all([
      request<Dashboard>("/platform/dashboard", {}, activeToken),
      request<Tenant[]>("/platform/tenants", {}, activeToken),
    ]);
    setDashboard(stats); setTenants(clients);
    if (selected) setSelected(clients.find((item) => item.id === selected.id) ?? null);
  }
  useEffect(() => { void load().catch((reason) => setError(readError(reason))); }, [token]);

  if (!token) return <PlatformLogin onAuthenticated={(next) => { window.localStorage.setItem(storageKey,next); setToken(next); }} />;

  async function createTenant(event: FormEvent) {
    event.preventDefault(); setError(null);
    try {
      const created = await request<Tenant>("/platform/tenants", {method:"POST",body:JSON.stringify(form)}, token);
      setForm(emptyTenant); setCreating(false); setSelected(created); await load();
    } catch (reason) { setError(readError(reason)); }
  }
  async function toggleStatus(tenant: Tenant) {
    try {
      const updated = await request<Tenant>(`/platform/tenants/${tenant.id}/status`, {method:"PATCH",body:JSON.stringify({status:tenant.status === "active" ? "inactive" : "active"})}, token);
      setSelected(updated); await load();
    } catch (reason) { setError(readError(reason)); }
  }

  return <main className="platform-page page-stack">
    <header className="page-header platform-header"><div><span className="eyebrow">ImobIA Platform</span><h1>Administração da plataforma</h1><p>Clientes, operação, integrações e consumo em um ambiente separado.</p></div><button className="button-outline" onClick={() => {window.localStorage.removeItem(storageKey);setToken(null);}} type="button"><LogOut size={16}/>Sair</button></header>
    {error ? <div className="error-box">{error}</div> : null}
    <section className="metrics-grid">
      <MetricCard icon={Building2} label="Clientes ativos" value={dashboard?.active_clients ?? 0} detail={`${dashboard?.inactive_clients ?? 0} inativos`} />
      <MetricCard icon={Users} label="Usuários" value={dashboard?.total_users ?? 0} detail="Em todas as imobiliárias" />
      <MetricCard icon={MessageSquare} label="Conversas" value={dashboard?.conversations ?? 0} detail={`${dashboard?.leads ?? 0} leads`} />
      <MetricCard icon={Bot} label="Chamadas de IA" value={dashboard?.ai_calls ?? 0} detail={`Custo estimado: R$ ${dashboard?.estimated_ai_cost ?? "0"}`} />
    </section>
    <div className="platform-layout">
      <Card><div className="section-inline-header"><div><h2>Imobiliárias clientes</h2><span>{dashboard?.total_clients ?? 0} cadastradas</span></div><button onClick={() => {setCreating(true);setSelected(null);}} type="button"><Plus size={15}/>Novo cliente</button></div>
        <div className="contacts-list">{tenants.map((tenant) => <button className={selected?.id === tenant.id ? "contact-row active" : "contact-row"} key={tenant.id} onClick={() => {setCreating(false);setSelected(tenant);}} type="button"><span className="conversation-avatar"><Building2 size={16}/></span><span><strong>{tenant.name}</strong><small>{tenant.slug} · {tenant.users} usuários</small></span><i className={tenant.status === "active" ? "status-dot active" : "status-dot"}/></button>)}</div>
      </Card>
      <Card>{creating ? <form className="page-stack" onSubmit={createTenant}><div><span className="eyebrow">Onboarding</span><h2>Novo cliente</h2></div><div className="form-grid"><Field label="Imobiliária" value={form.name} onChange={(name)=>setForm({...form,name})}/><Field label="Slug" value={form.slug} onChange={(slug)=>setForm({...form,slug})}/><Field label="Administrador" value={form.admin_name} onChange={(admin_name)=>setForm({...form,admin_name})}/><Field label="Email" type="email" value={form.admin_email} onChange={(admin_email)=>setForm({...form,admin_email})}/><Field label="Senha inicial" type="password" value={form.admin_password} onChange={(admin_password)=>setForm({...form,admin_password})}/></div><button type="submit">Criar imobiliária e administrador</button></form> : selected ? <TenantDetail tenant={selected} onToggle={() => void toggleStatus(selected)}/> : <div className="empty-state large"><ShieldCheck size={28}/>Selecione um cliente para ver os detalhes.</div>}</Card>
    </div>
  </main>;
}

function PlatformLogin({onAuthenticated}:{onAuthenticated:(token:string)=>void}) {
  const [email,setEmail]=useState(""); const [password,setPassword]=useState(""); const [error,setError]=useState<string|null>(null);
  async function submit(event:FormEvent){event.preventDefault();try{const result=await request<{access_token:string}>("/platform/auth/login",{method:"POST",body:JSON.stringify({email,password})});onAuthenticated(result.access_token);}catch(reason){setError(readError(reason));}}
  return <main className="login-page"><div className="login-heading"><ShieldCheck size={36}/><h1>ImobIA Platform</h1><p>Acesso exclusivo da administração</p></div><form className="login-card" onSubmit={submit}><label>Email<input onChange={(e)=>setEmail(e.target.value)} type="email" value={email}/></label><label>Senha<input onChange={(e)=>setPassword(e.target.value)} type="password" value={password}/></label>{error?<div className="error-box">{error}</div>:null}<button type="submit">Entrar</button></form></main>;
}
function TenantDetail({tenant,onToggle}:{tenant:Tenant;onToggle:()=>void}) { return <div className="page-stack"><div><span className="eyebrow">Cliente</span><h2>{tenant.name}</h2><p>{tenant.slug} · criado em {new Date(tenant.created_at).toLocaleDateString("pt-BR")}</p></div><div className="contact-info-grid"><div><Users size={15}/><span>{tenant.users} usuários</span></div><div><span>{tenant.contacts} contatos</span></div><div><span>{tenant.properties} imóveis</span></div><div><span>{tenant.conversations} conversas</span></div><div><span>{tenant.leads} leads</span></div><div><span>{tenant.ai_calls} chamadas IA · R$ {tenant.estimated_ai_cost}</span></div></div><div><h3>Integrações</h3><p>{Object.entries(tenant.integrations).map(([name,status])=>`${name}: ${status}`).join(" · ")||"Nenhuma integração configurada"}</p></div><button className={tenant.status === "active" ? "button-danger" : ""} onClick={onToggle} type="button">{tenant.status === "active" ? "Suspender cliente" : "Reativar cliente"}</button></div>; }
function Field({label,value,onChange,type="text"}:{label:string;value:string;onChange:(value:string)=>void;type?:string}) { return <label>{label}<input onChange={(e)=>onChange(e.target.value)} required type={type} value={value}/></label>; }
function readError(error:unknown){return error instanceof Error?error.message:"Falha na administração da plataforma.";}
