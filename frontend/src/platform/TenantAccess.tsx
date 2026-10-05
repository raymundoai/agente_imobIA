import { Copy, KeyRound } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../api/client";

type TenantUser = { id: string; name: string; email: string; role: string; status: string; is_master: boolean };
type PasswordLink = { link: string | null; token: string; expires_at: string };

const ROLE_LABELS: Record<string, string> = { admin: "Administrador", gestor: "Gestor", corretor: "Corretor", atendente: "Atendente" };

/** People in the client account; a forgotten password is solved with a one-time link. */
export function TenantAccess({ tenantId, token }: { tenantId: string; token: string }) {
  const [users, setUsers] = useState<TenantUser[]>([]);
  const [generated, setGenerated] = useState<{ userId: string; link: string; expiresAt: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    setGenerated(null);
    request<TenantUser[]>(`/platform/tenants/${tenantId}/users`, {}, token)
      .then(setUsers)
      .catch((reason) => setFeedback(reason instanceof Error ? reason.message : "Falha ao carregar usuários."));
  }, [tenantId, token]);

  async function generate(user: TenantUser) {
    if (!window.confirm(`Gerar um link de nova senha para ${user.name}? As sessões abertas dessa pessoa serão encerradas.`)) return;
    setFeedback(null);
    setCopied(false);
    try {
      const result = await request<PasswordLink>(`/platform/tenants/${tenantId}/users/${user.id}/password-link`, { method: "POST" }, token);
      // Without APP_PUBLIC_URL the API cannot know the panel address; this window's own address is a poor
      // guess (it is the admin), so the token is shown with the path to complete by hand.
      const link = result.link ?? `https://SEU-PAINEL/aceitar-convite?token=${encodeURIComponent(result.token)}`;
      setGenerated({ userId: user.id, link, expiresAt: result.expires_at });
    } catch (reason) {
      setFeedback(reason instanceof Error ? reason.message : "Não foi possível gerar o link.");
    }
  }

  async function copy(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setFeedback("Não foi possível copiar. Selecione o link e copie manualmente.");
    }
  }

  return (
    <div className="settings-subsection">
      <h3>Acessos</h3>
      <p className="field-hint">Se alguém esquecer a senha, gere um link e envie pelo WhatsApp. Ele vale por 7 dias e só pode ser usado uma vez.</p>
      <ul className="tenant-users">
        {users.map((user) => (
          <li key={user.id}>
            <span>
              <strong>{user.name}{user.is_master ? " · principal" : ""}</strong>
              <small>{user.email} · {ROLE_LABELS[user.role] ?? user.role}{user.status !== "active" ? ` · ${user.status === "invited" ? "convidado" : "inativo"}` : ""}</small>
            </span>
            <button className="secondary-button" onClick={() => void generate(user)} type="button">
              <KeyRound size={14} /> Link de nova senha
            </button>
            {generated?.userId === user.id ? (
              <div className="password-link">
                <input aria-label="Link de nova senha" onFocus={(event) => event.target.select()} readOnly value={generated.link} />
                <button className="secondary-button" onClick={() => void copy(generated.link)} type="button">
                  <Copy size={14} /> {copied ? "Copiado" : "Copiar"}
                </button>
                <small>Válido até {new Date(generated.expiresAt).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}.</small>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {feedback ? <p className="field-hint" role="status">{feedback}</p> : null}
    </div>
  );
}
