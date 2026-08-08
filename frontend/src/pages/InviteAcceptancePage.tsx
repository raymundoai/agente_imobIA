import { FormEvent, useMemo, useState } from "react";
import { ArrowRight, CheckCircle2, Hexagon } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

export function InviteAcceptancePage() {
  const { acceptInvitation } = useAuth();
  const token = useMemo(
    () => new URLSearchParams(window.location.search).get("token") ?? "",
    [],
  );
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) {
      setError("Este link de convite está incompleto.");
      return;
    }
    if (password.length < 12) {
      setError("Use uma senha com pelo menos 12 caracteres.");
      return;
    }
    if (password !== confirmation) {
      setError("As senhas não coincidem.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await acceptInvitation(token, password);
      window.history.replaceState({}, "", "/");
      setCompleted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível aceitar o convite.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-glow" />
      <div className="login-heading">
        <div className="login-logo"><Hexagon size={28} strokeWidth={2.4} /></div>
        <h1>ImobIA</h1>
        <p>Ative seu acesso à equipe</p>
      </div>
      {completed ? (
        <section className="login-card invite-complete-card">
          <CheckCircle2 aria-hidden="true" size={34} />
          <div>
            <span className="eyebrow">Acesso ativado</span>
            <h1>Tudo pronto</h1>
            <p>Sua senha foi definida e sua sessão já está protegida.</p>
          </div>
          <button onClick={() => window.location.assign("/")} type="button">
            Entrar no painel <ArrowRight size={16} />
          </button>
        </section>
      ) : (
        <form className="login-card" onSubmit={submit}>
          <div>
            <span className="eyebrow">Convite da equipe</span>
            <h1>Defina sua senha</h1>
            <p>O link é individual e deixará de funcionar depois do uso.</p>
          </div>
          <label>
            Nova senha
            <input
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
            />
            <small>Use pelo menos 12 caracteres.</small>
          </label>
          <label>
            Confirmar senha
            <input
              autoComplete="new-password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              type="password"
            />
          </label>
          {error ? <div className="error-box">{error}</div> : null}
          <button disabled={loading || !token} type="submit">
            {loading ? "Ativando..." : "Ativar acesso"}
            {!loading ? <ArrowRight size={16} /> : null}
          </button>
        </form>
      )}
    </main>
  );
}
