import { Mail, Phone, Plus, Search, Tags, UserRoundCog, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";

type ContactKind = "lead" | "tenant" | "owner" | "client";
type Contact = {
  id: string; name: string; phone: string; email: string | null; kind: ContactKind;
  status: "active" | "inactive"; tags: string[]; interest: string | null;
  notes: string | null; updated_at: string;
};
type ContactForm = Omit<Contact, "id" | "updated_at">;

const emptyForm: ContactForm = {
  name: "", phone: "", email: "", kind: "lead", status: "active",
  tags: [], interest: "", notes: "",
};

export function ContactsPage() {
  const { token } = useAuth();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | ContactKind>("all");
  const [form, setForm] = useState<ContactForm>(emptyForm);
  const [creating, setCreating] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    const items = await request<Contact[]>("/contacts", {}, token);
    setContacts(items);
    setSelectedId((current) => current || items[0]?.id || "");
    setLoadError(null);
    setLoading(false);
  }

  useEffect(() => { void load().catch((error) => { setLoadError(readError(error)); setLoading(false); }); }, [token]);
  const selected = contacts.find((item) => item.id === selectedId) ?? null;
  useEffect(() => {
    if (selected) setForm(toForm(selected));
  }, [selectedId, contacts]);

  const filtered = useMemo(() => contacts.filter((contact) => {
    const text = query.toLowerCase();
    return (filter === "all" || contact.kind === filter) &&
      [contact.name, contact.phone, contact.email, ...contact.tags].join(" ").toLowerCase().includes(text);
  }), [contacts, filter, query]);

  async function save() {
    setFeedback(null);
    try {
      const payload = { ...form, email: form.email || null, interest: form.interest || null, notes: form.notes || null };
      const saved = await request<Contact>(creating ? "/contacts" : `/contacts/${selectedId}`, {
        method: creating ? "POST" : "PATCH", body: JSON.stringify(payload),
      }, token);
      setContacts((current) => creating ? [...current, saved] : current.map((item) => item.id === saved.id ? saved : item));
      setSelectedId(saved.id); setCreating(false); setFeedback("Contato salvo no backend.");
    } catch (error) { setFeedback(readError(error)); }
  }

  return <section className="contacts-page">
    <div className="contacts-toolbar">
      <div className="property-tabs">{filters.map((item) => <button className={filter === item.key ? "active" : ""} key={item.key} onClick={() => setFilter(item.key)} type="button">{item.label}</button>)}</div>
      <button className="button-outline" onClick={() => { setCreating(true); setForm(emptyForm); }} type="button"><Plus size={15} />Novo contato</button>
    </div>
    {feedback ? <div className="inline-feedback">{feedback}</div> : null}
    <div className="contacts-layout">
      <section className="contacts-list-panel">
        <label className="inbox-search"><Search size={16} /><input onChange={(event) => setQuery(event.target.value)} placeholder="Buscar por nome, telefone, email ou tag" value={query} /></label>
        <div className="contacts-list">
          {loading ? <div className="empty-state" aria-live="polite">Carregando contatos...</div> : null}
          {loadError ? <div className="error-box" role="alert">{loadError}</div> : null}
          {!loading && !loadError && filtered.length === 0 ? <div className="empty-state">Nenhum contato encontrado.</div> : null}
          {filtered.map((contact) => <button className={contact.id === selectedId && !creating ? "contact-row active" : "contact-row"} key={contact.id} onClick={() => { setCreating(false); setSelectedId(contact.id); }} type="button"><span className="conversation-avatar"><UserRoundCog size={16} /></span><span><strong>{contact.name}</strong><small>{contact.phone}</small><span className="tag-row">{contact.tags.slice(0, 2).map((tag) => <i key={tag}>{tag}</i>)}</span></span><Badge variant={contact.kind === "lead" ? "accent" : "success"}>{kindLabels[contact.kind]}</Badge></button>)}
        </div>
      </section>
      <aside className="contact-detail-panel">
        <div className="contact-detail-header"><div><span className="eyebrow">{creating ? "Novo cadastro" : "Cadastro"}</span><h2>{creating ? "Novo contato" : selected?.name ?? "Selecione um contato"}</h2></div>{creating ? <button className="icon-button" onClick={() => setCreating(false)} type="button"><X size={18} /></button> : null}</div>
        <div className="contact-info-grid"><div><Phone size={15}/><span>{form.phone || "—"}</span></div><div><Mail size={15}/><span>{form.email || "—"}</span></div><div><Tags size={15}/><span>{form.tags.join(", ") || "—"}</span></div></div>
        <div className="settings-subsection"><div className="form-grid">
          <label>Nome<input onChange={(e) => setForm({...form, name:e.target.value})} value={form.name}/></label>
          <label>Tipo<select onChange={(e) => setForm({...form, kind:e.target.value as ContactKind})} value={form.kind}><option value="lead">Lead</option><option value="tenant">Inquilino</option><option value="owner">Proprietário</option><option value="client">Cliente</option></select></label>
          <label>Telefone<input onChange={(e) => setForm({...form, phone:e.target.value})} value={form.phone}/></label>
          <label>Email<input onChange={(e) => setForm({...form, email:e.target.value})} type="email" value={form.email ?? ""}/></label>
          <label className="form-span-2">Tags<input onChange={(e) => setForm({...form, tags:e.target.value.split(",").map((tag) => tag.trim()).filter(Boolean)})} value={form.tags.join(", ")}/></label>
          <label className="form-span-2">Interesse<input onChange={(e) => setForm({...form, interest:e.target.value})} value={form.interest ?? ""}/></label>
          <label className="form-span-2">Observações<textarea onChange={(e) => setForm({...form, notes:e.target.value})} value={form.notes ?? ""}/></label>
        </div></div>
        <div className="settings-actions"><span>{selected ? `Atualizado em ${new Date(selected.updated_at).toLocaleString("pt-BR")}` : ""}</span><button disabled={!form.name.trim() || !form.phone.trim()} onClick={() => void save()} type="button">Salvar alterações</button></div>
      </aside>
    </div>
  </section>;
}

const filters: Array<{key:"all"|ContactKind; label:string}> = [{key:"all",label:"Todos"},{key:"lead",label:"Leads"},{key:"tenant",label:"Inquilinos"},{key:"owner",label:"Proprietários"},{key:"client",label:"Clientes"}];
const kindLabels: Record<ContactKind,string> = {lead:"Lead",tenant:"Inquilino",owner:"Proprietário",client:"Cliente"};
function toForm(contact: Contact): ContactForm { const {id:_, updated_at:__, ...form}=contact; return form; }
function readError(error: unknown) { return error instanceof Error ? error.message : "Falha ao carregar contatos."; }
