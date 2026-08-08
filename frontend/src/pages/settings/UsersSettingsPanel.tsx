import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Check,
  Clipboard,
  Clock3,
  Crown,
  KeyRound,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  Trash2,
  UserRoundCheck,
  UserRoundX,
  UsersRound,
  X,
} from "lucide-react";
import { request } from "../../api/client";
import type { PasswordSetup, User, UserAudit } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";
import { validateNewUserForm } from "../../lib/settingsValidation";

type InviteForm = {
  name: string;
  email: string;
  role: User["role"];
};

type EditForm = Pick<User, "name" | "email" | "role">;
type StatusFilter = "all" | User["status"];
type RoleFilter = "all" | User["role"];

const emptyInvite: InviteForm = { name: "", email: "", role: "corretor" };
const roles: User["role"][] = ["admin", "gestor", "corretor", "atendente"];
const roleLabels: Record<User["role"], string> = {
  admin: "Administrador",
  gestor: "Gestor",
  corretor: "Corretor",
  atendente: "Atendente",
};
const statusLabels: Record<User["status"], string> = {
  active: "Ativo",
  inactive: "Inativo",
  invited: "Convite pendente",
};
const auditLabels: Record<string, string> = {
  user_created: "criou o usuário",
  user_invited: "convidou",
  user_updated: "atualizou",
  invitation_renewed: "renovou o convite de",
  password_reset_created: "gerou redefinição de senha para",
  sessions_revoked: "encerrou as sessões de",
  password_defined: "definiu a senha de",
  password_changed: "alterou a própria senha",
  user_deleted: "excluiu o perfil de",
};

export function UsersSettingsPanel() {
  const { token, logout, changePassword } = useAuth();
  const claims = getTokenClaims(token);
  const canManage = claims?.role === "admin";
  const canViewTeam = claims?.role === "admin" || claims?.role === "gestor";
  const [me, setMe] = useState<User | null>(null);
  const isMaster = me?.is_master === true;
  const [users, setUsers] = useState<User[]>([]);
  const [audits, setAudits] = useState<UserAudit[]>([]);
  const [invite, setInvite] = useState<InviteForm>(emptyInvite);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [edit, setEdit] = useState<EditForm | null>(null);
  const [setup, setSetup] = useState<{ link: string; userName: string; expiresAt: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [operation, setOperation] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error">("success");
  const [passwords, setPasswords] = useState({ current: "", next: "", confirmation: "" });

  const inviteErrors = validateNewUserForm({ ...invite, password: "valid-placeholder" });
  delete inviteErrors.password;
  const inviteValid = Object.keys(inviteErrors).length === 0;

  async function loadData() {
    setLoading(true);
    try {
      const current = await request<User>("/users/me", {}, token);
      setMe(current);
      if (!canViewTeam) return;
      const [team, activity] = await Promise.all([
        request<User[]>("/users", {}, token),
        canManage
          ? request<UserAudit[]>("/users/audit?limit=30", {}, token)
          : Promise.resolve([]),
      ]);
      setUsers(team);
      setAudits(activity);
    } catch (error) {
      feedback(error, "Falha ao carregar a equipe.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, canManage, canViewTeam]);

  const filteredUsers = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("pt-BR");
    return users.filter((user) => {
      const matchesQuery = !term || `${user.name} ${user.email}`.toLocaleLowerCase("pt-BR").includes(term);
      const matchesStatus = statusFilter === "all" || user.status === statusFilter;
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      return matchesQuery && matchesStatus && matchesRole;
    });
  }, [query, roleFilter, statusFilter, users]);

  const counts = useMemo(() => ({
    active: users.filter((user) => user.status === "active").length,
    invited: users.filter((user) => user.status === "invited").length,
    admins: users.filter((user) => user.status === "active" && user.role === "admin").length,
  }), [users]);

  function feedback(error: unknown, fallback: string) {
    setMessage(error instanceof Error ? error.message : fallback);
    setMessageKind("error");
  }

  function showSetup(result: PasswordSetup) {
    const link = `${window.location.origin}/aceitar-convite?token=${encodeURIComponent(result.token)}`;
    setSetup({ link, userName: result.user.name, expiresAt: result.expires_at });
    setCopied(false);
  }

  async function inviteUser() {
    if (!inviteValid || !canManage) return;
    setOperation("invite");
    setMessage(null);
    try {
      const result = await request<PasswordSetup>(
        "/users/invitations",
        { method: "POST", body: JSON.stringify(invite) },
        token,
      );
      showSetup(result);
      setInvite(emptyInvite);
      setMessage("Convite criado. Copie o link e envie à pessoa convidada.");
      setMessageKind("success");
      await loadData();
    } catch (error) {
      feedback(error, "Falha ao criar convite.");
    } finally {
      setOperation(null);
    }
  }

  async function copySetupLink() {
    if (!setup) return;
    try {
      await navigator.clipboard.writeText(setup.link);
      setCopied(true);
    } catch {
      feedback(null, "Não foi possível copiar automaticamente. Selecione o link manualmente.");
    }
  }

  async function patchUser(user: User, patch: Partial<Pick<User, "name" | "email" | "role" | "status">>) {
    setOperation(user.id);
    setMessage(null);
    try {
      const updated = await request<User>(
        `/users/${user.id}`,
        { method: "PATCH", body: JSON.stringify(patch) },
        token,
      );
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (updated.id === me?.id) setMe(updated);
      setEditingId(null);
      setEdit(null);
      setMessage("Usuário atualizado.");
      setMessageKind("success");
      await refreshAudit();
    } catch (error) {
      feedback(error, "Falha ao atualizar usuário.");
    } finally {
      setOperation(null);
    }
  }

  async function refreshAudit() {
    if (!canManage) return;
    try {
      setAudits(await request<UserAudit[]>("/users/audit?limit=30", {}, token));
    } catch {
      // A alteração principal já foi concluída; o histórico será atualizado no próximo carregamento.
    }
  }

  async function toggleStatus(user: User) {
    const next = user.status === "active" ? "inactive" : "active";
    const action = next === "inactive" ? "desativar" : "reativar";
    if (!window.confirm(`Deseja ${action} o acesso de ${user.name}?`)) return;
    await patchUser(user, { status: next });
  }

  async function generateSetup(user: User) {
    const label = user.status === "invited" ? "renovar o convite" : "gerar um link de redefinição de senha";
    if (!window.confirm(`Deseja ${label} para ${user.name}? Links anteriores deixarão de funcionar.`)) return;
    setOperation(user.id);
    try {
      const result = await request<PasswordSetup>(
        `/users/${user.id}/password-setup`,
        { method: "POST" },
        token,
      );
      showSetup(result);
      setUsers((current) => current.map((item) => item.id === result.user.id ? result.user : item));
      setMessage(user.status === "invited" ? "Convite renovado." : "Link de redefinição criado e sessões anteriores encerradas.");
      setMessageKind("success");
      await refreshAudit();
    } catch (error) {
      feedback(error, "Falha ao gerar o link.");
    } finally {
      setOperation(null);
    }
  }

  async function revokeSessions(user: User) {
    if (!window.confirm(`Encerrar todas as sessões abertas de ${user.name}?`)) return;
    setOperation(user.id);
    try {
      await request<User>(`/users/${user.id}/revoke-sessions`, { method: "POST" }, token);
      if (user.id === claims?.userId) {
        logout();
        return;
      }
      setMessage("Sessões encerradas imediatamente.");
      setMessageKind("success");
      await refreshAudit();
    } catch (error) {
      feedback(error, "Falha ao encerrar sessões.");
    } finally {
      setOperation(null);
    }
  }

  async function deleteUser(user: User) {
    if (!isMaster || user.is_master) return;
    if (!window.confirm(`Excluir permanentemente o perfil de ${user.name}? O histórico operacional será preservado, mas essa pessoa perderá todo o acesso.`)) return;
    setOperation(user.id);
    setMessage(null);
    try {
      await request<void>(`/users/${user.id}`, { method: "DELETE" }, token);
      setUsers((current) => current.filter((item) => item.id !== user.id));
      setEditingId(null);
      setEdit(null);
      setMessage("Perfil excluído permanentemente.");
      setMessageKind("success");
      await refreshAudit();
    } catch (error) {
      feedback(error, "Falha ao excluir o perfil.");
    } finally {
      setOperation(null);
    }
  }

  async function submitPasswordChange() {
    if (passwords.next.length < 12) {
      feedback(null, "A nova senha deve ter pelo menos 12 caracteres.");
      return;
    }
    if (passwords.next !== passwords.confirmation) {
      feedback(null, "A confirmação da nova senha não coincide.");
      return;
    }
    setOperation("password");
    try {
      await changePassword(passwords.current, passwords.next);
      setPasswords({ current: "", next: "", confirmation: "" });
      setMessage("Senha alterada e sessões anteriores encerradas.");
      setMessageKind("success");
      await refreshAudit();
    } catch (error) {
      feedback(error, "Falha ao alterar a senha.");
    } finally {
      setOperation(null);
    }
  }

  return (
    <div className="team-settings-stack">
      <Card className="settings-panel-card team-overview-card">
        <div className="settings-panel-header">
          <div>
            <h2>Equipe e acessos</h2>
            <p>Gerencie convites, permissões e segurança de cada pessoa.</p>
          </div>
          <Badge variant={canManage ? "success" : canViewTeam ? "accent" : "muted"}>
            {isMaster ? "Administrador principal" : canManage ? "Administrador" : canViewTeam ? "Visualização" : "Perfil pessoal"}
          </Badge>
        </div>
        {canViewTeam ? (
          <div className="team-metrics" aria-label="Resumo da equipe">
            <TeamMetric icon={<UsersRound size={18} />} label="Pessoas ativas" value={counts.active} />
            <TeamMetric icon={<Clock3 size={18} />} label="Convites pendentes" value={counts.invited} />
            <TeamMetric icon={<ShieldCheck size={18} />} label="Administradores" value={counts.admins} />
          </div>
        ) : (
          <div className="settings-readonly-note">Seu perfil não permite visualizar os dados dos demais integrantes.</div>
        )}
        {message ? <div className={`team-feedback ${messageKind}`} role={messageKind === "error" ? "alert" : "status"}>{message}</div> : null}
      </Card>

      {canManage ? (
        <Card className="settings-panel-card team-invite-card">
          <div className="settings-panel-header compact">
            <div>
              <h2>Convidar pessoa</h2>
              <p>Ela definirá a própria senha por um link individual, válido por sete dias.</p>
            </div>
            <UserRoundCheck aria-hidden="true" size={22} />
          </div>
          <div className="form-grid">
            <label>Nome<input value={invite.name} onChange={(event) => setInvite((current) => ({ ...current, name: event.target.value }))} /></label>
            <label>Email<input type="email" value={invite.email} onChange={(event) => setInvite((current) => ({ ...current, email: event.target.value }))} /></label>
            <label>Perfil<select value={invite.role} onChange={(event) => setInvite((current) => ({ ...current, role: event.target.value as User["role"] }))}>{roles.map((role) => <option key={role} value={role}>{roleLabels[role]}</option>)}</select></label>
          </div>
          <div className="settings-actions"><span>O sistema não envia ou exibe senhas.</span><button disabled={!inviteValid || operation === "invite"} onClick={() => void inviteUser()} type="button"><Plus size={16} />{operation === "invite" ? "Criando..." : "Criar convite"}</button></div>
          {setup ? (
            <div className="invite-link-box">
              <div><strong>Link para {setup.userName}</strong><small>Expira em {formatDate(setup.expiresAt)}</small></div>
              <input aria-label="Link de convite" readOnly value={setup.link} />
              <button className="secondary-button" onClick={() => void copySetupLink()} type="button">{copied ? <Check size={16} /> : <Clipboard size={16} />}{copied ? "Copiado" : "Copiar link"}</button>
            </div>
          ) : null}
        </Card>
      ) : null}

      {canViewTeam ? (
        <Card className="settings-panel-card team-directory-card">
          <div className="settings-panel-header compact"><div><h2>Pessoas</h2><p>{filteredUsers.length} de {users.length} integrantes exibidos.</p></div></div>
          <div className="team-filters">
            <label className="team-search"><Search size={16} /><input aria-label="Buscar pessoa" placeholder="Buscar por nome ou email" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
            <select aria-label="Filtrar por perfil" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value as RoleFilter)}><option value="all">Todos os perfis</option>{roles.map((role) => <option key={role} value={role}>{roleLabels[role]}</option>)}</select>
            <select aria-label="Filtrar por status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}><option value="all">Todos os status</option><option value="active">Ativos</option><option value="inactive">Inativos</option><option value="invited">Convites pendentes</option></select>
          </div>
          {loading ? <div className="empty-state">Carregando equipe...</div> : null}
          {!loading && filteredUsers.length === 0 ? <div className="empty-state">Nenhuma pessoa corresponde aos filtros.</div> : null}
          <div className="team-user-list">
            {filteredUsers.map((user) => {
              const isMe = user.id === claims?.userId;
              const isEditing = editingId === user.id && edit;
              return (
                <article className={`team-user-card ${user.status !== "active" ? "is-muted" : ""}`} key={user.id}>
                  <div className="team-user-avatar" aria-hidden="true">{initials(user.name)}</div>
                  <div className="team-user-main">
                    {isEditing ? (
                      <div className="team-edit-grid">
                        <label>Nome<input value={edit.name} onChange={(event) => setEdit({ ...edit, name: event.target.value })} /></label>
                        <label>Email<input type="email" value={edit.email} onChange={(event) => setEdit({ ...edit, email: event.target.value })} /></label>
                        <label>Perfil<select disabled={isMe || user.is_master} value={edit.role} onChange={(event) => setEdit({ ...edit, role: event.target.value as User["role"] })}>{roles.map((role) => <option key={role} value={role}>{roleLabels[role]}</option>)}</select></label>
                      </div>
                    ) : (
                      <><div className="team-user-title"><strong>{user.name}</strong>{user.is_master ? <Badge variant="accent"><Crown size={12} />Principal</Badge> : null}{isMe ? <Badge variant="accent">Você</Badge> : null}<Badge variant={user.status === "active" ? "success" : user.status === "invited" ? "accent" : "muted"}>{statusLabels[user.status]}</Badge></div><span>{user.email}</span><small>{roleLabels[user.role]} · Último acesso: {user.last_login_at ? formatDate(user.last_login_at) : "ainda não acessou"}</small></>
                    )}
                  </div>
                  {canManage ? (
                    <div className="team-user-actions">
                      {isEditing ? <><button aria-label={`Salvar ${user.name}`} onClick={() => void patchUser(user, edit)} type="button"><Check size={15} />Salvar</button><button className="ghost-button" onClick={() => { setEditingId(null); setEdit(null); }} type="button"><X size={15} />Cancelar</button></> : <button onClick={() => { setEditingId(user.id); setEdit({ name: user.name, email: user.email, role: user.role }); }} type="button"><Pencil size={15} />Editar</button>}
                      {!isMe && !isEditing && user.status !== "invited" ? <button className="ghost-button" onClick={() => void toggleStatus(user)} type="button">{user.status === "active" ? <UserRoundX size={15} /> : <UserRoundCheck size={15} />}{user.status === "active" ? "Desativar" : "Reativar"}</button> : null}
                      {!isMe && !isEditing && user.status !== "inactive" ? <button className="ghost-button" onClick={() => void generateSetup(user)} type="button">{user.status === "invited" ? <RotateCcw size={15} /> : <KeyRound size={15} />}{user.status === "invited" ? "Renovar convite" : "Redefinir senha"}</button> : null}
                      {!isEditing && user.status === "active" ? <button className="ghost-button" onClick={() => void revokeSessions(user)} type="button"><ShieldCheck size={15} />Encerrar sessões</button> : null}
                      {isMaster && !user.is_master && !isEditing ? <button className="button-danger" onClick={() => void deleteUser(user)} type="button"><Trash2 size={15} />Excluir</button> : null}
                      {operation === user.id ? <small>Processando...</small> : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </Card>
      ) : null}

      <Card className="settings-panel-card team-password-card">
        <div className="settings-panel-header compact"><div><h2>Minha segurança</h2><p>{me ? `${me.name} · ${me.email}` : "Altere sua senha de acesso."}</p></div><KeyRound aria-hidden="true" size={22} /></div>
        <div className="team-password-form">
          <label>Senha atual<input autoComplete="current-password" type="password" value={passwords.current} onChange={(event) => setPasswords((current) => ({ ...current, current: event.target.value }))} /></label>
          <label>Nova senha<input autoComplete="new-password" type="password" value={passwords.next} onChange={(event) => setPasswords((current) => ({ ...current, next: event.target.value }))} /><small>Mínimo de 12 caracteres.</small></label>
          <label>Confirmar nova senha<input autoComplete="new-password" type="password" value={passwords.confirmation} onChange={(event) => setPasswords((current) => ({ ...current, confirmation: event.target.value }))} /></label>
        </div>
        <div className="settings-actions"><span>Ao alterar, todas as outras sessões serão encerradas.</span><button disabled={operation === "password" || !passwords.current || !passwords.next || !passwords.confirmation} onClick={() => void submitPasswordChange()} type="button">{operation === "password" ? "Alterando..." : "Alterar senha"}</button></div>
      </Card>

      {canManage && audits.length > 0 ? (
        <Card className="settings-panel-card team-audit-card">
          <div className="settings-panel-header compact"><div><h2>Atividade de acessos</h2><p>Últimas alterações administrativas da equipe.</p></div></div>
          <div className="team-audit-list">{audits.map((audit) => <div key={audit.id}><Clock3 size={15} /><span><strong>{userName(users, audit.actor_user_id)}</strong> {auditLabels[audit.action] ?? audit.action} <strong>{auditTargetName(users, audit)}</strong></span><time>{formatDate(audit.created_at)}</time></div>)}</div>
        </Card>
      ) : null}
    </div>
  );
}

function TeamMetric({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return <div>{icon}<span>{label}</span><strong>{value}</strong></div>;
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "?";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function userName(users: User[], id: string | null) {
  if (!id) return "Sistema";
  return users.find((user) => user.id === id)?.name ?? "Usuário removido";
}

function auditTargetName(users: User[], audit: UserAudit) {
  if (audit.target_user_id) return userName(users, audit.target_user_id);
  return typeof audit.changes.name === "string" ? audit.changes.name : "Usuário removido";
}
