import { useEffect, useState } from "react";
import { request } from "../api/client";
import { Card } from "../components/Card";

type Invitation = {
  id: string;
  code_suffix: string;
  created_at: string;
  expires_at: string;
  redeemed_at: string | null;
  revoked_at: string | null;
};

type CreatedInvitation = Invitation & { code: string };

function status(invitation: Invitation) {
  if (invitation.redeemed_at) return "Utilizado";
  if (invitation.revoked_at) return "Revogado";
  if (new Date(invitation.expires_at) <= new Date()) return "Expirado";
  return "Disponível";
}

export function SignupInvitations({ token }: { token: string }) {
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [newCode, setNewCode] = useState<string | null>(null);
  const [validDays, setValidDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    request<Invitation[]>("/platform/signup-invitations", {}, token)
      .then(setInvitations)
      .catch((reason) => setFeedback(reason instanceof Error ? reason.message : "Não foi possível carregar os convites."));
  }, [token]);

  async function create() {
    setBusy(true);
    setFeedback(null);
    try {
      const invitation = await request<CreatedInvitation>(
        "/platform/signup-invitations",
        { method: "POST", body: JSON.stringify({ valid_days: validDays }) },
        token,
      );
      setInvitations((current) => [invitation, ...current]);
      setNewCode(invitation.code);
      setFeedback("Convite criado. Copie o código agora: ele não será mostrado novamente.");
    } catch (reason) {
      setFeedback(reason instanceof Error ? reason.message : "Não foi possível criar o convite.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(invitation: Invitation) {
    if (!window.confirm("Revogar este convite? O código deixará de funcionar.")) return;
    setFeedback(null);
    try {
      const updated = await request<Invitation>(
        `/platform/signup-invitations/${invitation.id}/revoke`,
        { method: "POST" },
        token,
      );
      setInvitations((current) => current.map((item) => item.id === updated.id ? updated : item));
      setFeedback("Convite revogado.");
    } catch (reason) {
      setFeedback(reason instanceof Error ? reason.message : "Não foi possível revogar o convite.");
    }
  }

  async function copyCode() {
    if (!newCode) return;
    try {
      await navigator.clipboard.writeText(newCode);
      setFeedback("Código copiado.");
    } catch {
      setFeedback("Não foi possível copiar automaticamente. Selecione o código acima para copiá-lo.");
    }
  }

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Convites para o beta</h2>
          <p>Crie um código por corretor. O cadastro aplica a condição beta automaticamente.</p>
        </div>
      </div>
      <div className="invitation-actions">
        <label>
          Validade em dias
          <input min={1} max={90} type="number" value={validDays} onChange={(event) => setValidDays(Number(event.target.value))} />
        </label>
        <button className="secondary-button" disabled={busy || validDays < 1 || validDays > 90} onClick={() => void create()} type="button">
          {busy ? "Criando..." : "Criar convite"}
        </button>
      </div>
      {newCode ? (
        <div className="invitation-created">
          <strong>Código gerado (mostrado uma vez)</strong>
          <code>{newCode}</code>
          <button className="secondary-button" onClick={() => void copyCode()} type="button">Copiar código</button>
        </div>
      ) : null}
      {feedback ? <p className="field-hint" role="status">{feedback}</p> : null}
      {invitations.length ? (
        <div className="invitation-list">
          {invitations.map((invitation) => (
            <div className="invitation-row" key={invitation.id}>
              <span>Convite ····{invitation.code_suffix}</span>
              <span>{status(invitation)} · vence {new Date(invitation.expires_at).toLocaleDateString("pt-BR")}</span>
              {status(invitation) === "Disponível" ? <button className="button-outline" onClick={() => void revoke(invitation)} type="button">Revogar</button> : null}
            </div>
          ))}
        </div>
      ) : <p className="field-hint">Nenhum convite criado ainda.</p>}
    </Card>
  );
}
