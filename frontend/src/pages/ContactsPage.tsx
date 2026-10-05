import { Mail, Phone, Plus, Search, Tags, Trash2, UserRoundCog, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "../api/client";
import type { Contact, ContactKind } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { getTokenClaims } from "../auth/tokenClaims";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import { mergeUserContactTags, TagInput, userContactTags } from "../components/TagInput";
import { formatPhone } from "../lib/format";
import { isOwnNumber } from "../lib/ownNumber";
import { useOwnNumber } from "../lib/useOwnNumber";

type ContactForm = Omit<Contact, "id" | "tenant_id" | "created_at" | "updated_at">;

const emptyForm: ContactForm = {
  name: "", phone: "", email: "", kind: "lead", status: "active",
  tags: [], interest: "", notes: "",
};

export function ContactsPage() {
  const { token } = useAuth();
  const ownNumber = useOwnNumber(token);
  // Decided by the number connected right now; a tag can be left over from a previous number.
  const isOwn = (contact: Contact) => isOwnNumber(contact.phone, ownNumber);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | ContactKind>("all");
  const [form, setForm] = useState<ContactForm>(emptyForm);
  const [creating, setCreating] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const role = getTokenClaims(token)?.role;
  const canDelete = role === "admin" || role === "gestor";

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

  function startCreating() {
    setCreating(true);
    setForm(emptyForm);
    setFeedback(null);
  }

  async function save() {
    setFeedback(null);
    try {
      const payload = { ...form, email: form.email || null, interest: form.interest || null, notes: form.notes || null };
      const saved = await request<Contact>(creating ? "/contacts" : `/contacts/${selectedId}`, {
        method: creating ? "POST" : "PATCH", body: JSON.stringify(payload),
      }, token);
      setContacts((current) => creating ? [...current, saved] : current.map((item) => item.id === saved.id ? saved : item));
      setSelectedId(saved.id); setFeedback(creating ? "Contato criado." : "Alterações salvas."); setCreating(false);
    } catch (error) { setFeedback(readError(error)); }
  }

  async function deleteSelected() {
    if (!selected) return;
    setDeleting(true);
    try {
      await request<void>(`/contacts/${selected.id}`, { method: "DELETE" }, token);
      setContacts((current) => current.filter((item) => item.id !== selected.id));
      setSelectedId("");
      setFeedback(`Contato ${selected.name} excluído. O registro fica em Configurações > Histórico.`);
      setConfirmingDelete(false);
    } catch (error) {
      setFeedback(readError(error));
      setConfirmingDelete(false);
    } finally {
      setDeleting(false);
    }
  }

  return <section className="contacts-page">
    <div className="contacts-toolbar">
      <div className="property-tabs">{filters.map((item) => <button className={filter === item.key ? "active" : ""} key={item.key} onClick={() => setFilter(item.key)} type="button">{item.label}</button>)}</div>
      <button className="primary-button" onClick={startCreating} type="button"><Plus size={15} />Novo contato</button>
    </div>
    {feedback ? <div className="inline-feedback">{feedback}</div> : null}
    <div className="contacts-layout">
      <section className="contacts-list-panel">
        <label className="inbox-search"><Search size={16} /><input onChange={(event) => setQuery(event.target.value)} placeholder="Buscar por nome, telefone, email ou tag" value={query} /></label>
        <div className="contacts-list">
          {loading ? <div className="empty-state" aria-live="polite">Carregando contatos...</div> : null}
          {loadError ? <div className="error-box" role="alert">{loadError}</div> : null}
          {!loading && !loadError && filtered.length === 0 ? (
            <p className="list-empty">
              {query.trim()
                ? `Nada encontrado para “${query.trim()}”.`
                : contacts.length === 0
                  ? "Nenhum contato ainda."
                  : `Nenhum contato do tipo ${filters.find((item) => item.key === filter)?.label.toLowerCase()}.`}
            </p>
          ) : null}
          {filtered.map((contact) => <button className={contact.id === selectedId && !creating ? "contact-row active" : "contact-row"} key={contact.id} onClick={() => { setCreating(false); setSelectedId(contact.id); }} type="button"><span className="conversation-avatar"><UserRoundCog size={16} /></span><span><strong>{contact.name}</strong><small>{formatPhone(contact.phone)}</small><span className="tag-row">{userContactTags(contact.tags).slice(0, 2).map((tag) => <i key={tag}>{tag}</i>)}</span></span>{isOwn(contact) ? <Badge variant="muted">Você</Badge> : <Badge variant={contact.kind === "lead" ? "accent" : "success"}>{kindLabels[contact.kind]}</Badge>}</button>)}
        </div>
      </section>
      {!creating && !selected ? (
        <aside className="contact-detail-panel contact-detail-empty">
          <div className="empty-guide">
            <h2>{contacts.length === 0 ? "Seus contatos aparecem aqui" : "Escolha um contato"}</h2>
            <p>
              {contacts.length === 0
                ? "Leads entram sozinhos quando conversam com o agente de IA. Proprietários, inquilinos e clientes você cadastra aqui."
                : "Selecione alguém na lista para ver e editar os dados, ou cadastre um novo contato."}
            </p>
            <button className="secondary-button" onClick={startCreating} type="button"><Plus size={15} />Novo contato</button>
          </div>
        </aside>
      ) : (
      <aside className="contact-detail-panel">
        <div className="contact-detail-header"><div><h2>{creating ? "Novo contato" : selected?.name}</h2>{!creating && selected && isOwn(selected) ? <span className="you-chip">Você · número conectado ao WhatsApp</span> : null}</div>{creating ? <button className="icon-button" onClick={() => setCreating(false)} type="button"><X size={18} /></button> : null}</div>
        <div className="contact-info-grid"><div><Phone size={15}/><span>{formatPhone(form.phone) || "—"}</span></div><div><Mail size={15}/><span>{form.email || "—"}</span></div><div><Tags size={15}/><span>{userContactTags(form.tags).join(", ") || "—"}</span></div></div>
        <div className="settings-subsection"><div className="form-grid">
          <label>Nome<input onChange={(e) => setForm({...form, name:e.target.value})} value={form.name}/></label>
          <label>Tipo<select onChange={(e) => setForm({...form, kind:e.target.value as ContactKind})} value={form.kind}><option value="lead">Lead</option><option value="tenant">Inquilino</option><option value="owner">Proprietário</option><option value="client">Cliente</option></select></label>
          <label>Telefone<input onChange={(e) => setForm({...form, phone:e.target.value})} value={form.phone}/></label>
          <label>Email<input onChange={(e) => setForm({...form, email:e.target.value})} type="email" value={form.email ?? ""}/></label>
          <label className="form-span-2">Tags<TagInput onChange={(tags) => setForm({...form, tags:mergeUserContactTags(form.tags, tags)})} tags={userContactTags(form.tags)}/><small>Pressione espaço, Enter ou vírgula para criar cada tag.</small></label>
          <label className="form-span-2">Interesse<input onChange={(e) => setForm({...form, interest:e.target.value})} value={form.interest ?? ""}/></label>
          <label className="form-span-2">Observações<textarea onChange={(e) => setForm({...form, notes:e.target.value})} value={form.notes ?? ""}/></label>
        </div></div>
        <div className="settings-actions">{selected && !creating && canDelete ? <button className="link-button danger-link" onClick={() => setConfirmingDelete(true)} type="button"><Trash2 size={15} />Excluir contato</button> : null}<span>{selected && !creating ? `Atualizado em ${new Date(selected.updated_at).toLocaleString("pt-BR")}` : ""}</span><button className="primary-button" disabled={!form.name.trim() || !form.phone.trim()} onClick={() => void save()} type="button">{creating ? "Criar contato" : "Salvar alterações"}</button></div>
      </aside>
      )}
    </div>
    {confirmingDelete && selected ? (
      <Modal
        footer={<>
          <button className="secondary-button" disabled={deleting} onClick={() => setConfirmingDelete(false)} type="button">Cancelar</button>
          <button className="primary-button button-danger" disabled={deleting} onClick={() => void deleteSelected()} type="button">{deleting ? "Excluindo..." : "Excluir contato"}</button>
        </>}
        onClose={() => setConfirmingDelete(false)}
        title={`Excluir ${selected.name}?`}
      >
        <p className="modal-text">
          O cadastro sai da lista de contatos. As conversas e demandas dessa pessoa continuam no sistema, e uma cópia do
          cadastro fica em Configurações &gt; Histórico.
        </p>
        <p className="modal-text muted">Se ela mandar mensagem de novo pelo WhatsApp, um contato novo é criado automaticamente.</p>
      </Modal>
    ) : null}
  </section>;
}

const filters: Array<{key:"all"|ContactKind; label:string}> = [{key:"all",label:"Todos"},{key:"lead",label:"Leads"},{key:"tenant",label:"Inquilinos"},{key:"owner",label:"Proprietários"},{key:"client",label:"Clientes"}];
const kindLabels: Record<ContactKind,string> = {lead:"Lead",tenant:"Inquilino",owner:"Proprietário",client:"Cliente"};
function toForm(contact: Contact): ContactForm {
  const {id:_, tenant_id:__, created_at:___, updated_at:____, ...form}=contact;
  return form;
}
function readError(error: unknown) { return error instanceof Error ? error.message : "Falha ao carregar contatos."; }
