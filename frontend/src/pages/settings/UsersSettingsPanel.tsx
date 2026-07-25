import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { User } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable";

type NewUserForm = {
  name: string;
  email: string;
  password: string;
  role: User["role"];
};

const emptyUser: NewUserForm = {
  name: "",
  email: "",
  password: "",
  role: "corretor",
};

const roles: User["role"][] = ["admin", "gestor", "corretor", "atendente"];
const roleLabels: Record<User["role"], string> = {
  admin: "Administrador",
  gestor: "Gestor",
  corretor: "Corretor",
  atendente: "Atendente",
};

export function UsersSettingsPanel() {
  const { token } = useAuth();
  const claims = getTokenClaims(token);
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState<NewUserForm>(emptyUser);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function loadUsers() {
    setLoading(true);
    try {
      setUsers(await request<User[]>("/users", {}, token));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao carregar usuários.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function createUser() {
    setLoading(true);
    setMessage(null);
    try {
      await request<User>(
        "/users",
        {
          method: "POST",
          body: JSON.stringify(form),
        },
        token,
      );
      setForm(emptyUser);
      setMessage("Usuário criado.");
      await loadUsers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao criar usuário.");
    } finally {
      setLoading(false);
    }
  }

  async function patchUser(user: User, patch: Partial<Pick<User, "role" | "status">>) {
    setMessage(null);
    try {
      const updated = await request<User>(
        `/users/${user.id}`,
        {
          method: "PATCH",
          body: JSON.stringify(patch),
        },
        token,
      );
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao atualizar usuário.");
    }
  }

  const canManage = claims?.role === "admin";

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Usuários</h2>
          <p>Cadastre quem pode acessar o painel da empresa.</p>
        </div>
        <Badge variant={canManage ? "success" : "muted"}>
          {canManage ? "Administrador" : "Somente leitura"}
        </Badge>
      </div>

      <div className="form-grid">
        <label>
          Nome
          <input
            disabled={!canManage}
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
          />
        </label>
        <label>
          Email
          <input
            disabled={!canManage}
            type="email"
            value={form.email}
            onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
          />
        </label>
        <label>
          Senha temporária
          <input
            disabled={!canManage}
            type="password"
            value={form.password}
            onChange={(event) =>
              setForm((current) => ({ ...current, password: event.target.value }))
            }
          />
        </label>
        <label>
          Perfil
          <select
            disabled={!canManage}
            value={form.role}
            onChange={(event) =>
              setForm((current) => ({ ...current, role: event.target.value as User["role"] }))
            }
          >
            {roles.map((role) => (
              <option key={role} value={role}>
                {roleLabels[role]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="settings-actions">
        {message ? <span>{message}</span> : null}
        <button disabled={!canManage || loading} onClick={createUser} type="button">
          {loading ? "Processando..." : "Criar usuário"}
        </button>
      </div>

      <DataTable
        data={users}
        empty="Nenhum usuário encontrado."
        columns={[
          { key: "name", label: "Nome", render: (item) => item.name },
          { key: "email", label: "Email", render: (item) => item.email },
          {
            key: "role",
            label: "Perfil",
            render: (item) => (
              <select
                disabled={!canManage}
                value={item.role}
                onChange={(event) =>
                  void patchUser(item, { role: event.target.value as User["role"] })
                }
              >
                {roles.map((role) => (
                  <option key={role} value={role}>
                    {roleLabels[role]}
                  </option>
                ))}
              </select>
            ),
          },
          {
            key: "status",
            label: "Status",
            render: (item) => (
              <select
                disabled={!canManage}
                value={item.status}
                onChange={(event) =>
                  void patchUser(item, { status: event.target.value as User["status"] })
                }
              >
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
              </select>
            ),
          },
        ]}
      />
    </Card>
  );
}
