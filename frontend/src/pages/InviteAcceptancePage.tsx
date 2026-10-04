import { FormEvent, useMemo, useState } from "react";
import { ArrowRight, CheckCircle2} from "lucide-react";
import { AuthLayout } from "../components/AuthLayout";
import { PasswordInput } from "../components/PasswordInput";
import { useAuth } from "../auth/AuthContext";

export function InviteAcceptancePage() {
  const { acceptInvitation } = useAuth();
  const token = useMemo(
    () => new URLSearchParams(window.location.search).get("token") ?? "",
    [],
  );
  const [password, setPassword] = useState("");
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
    <AuthLayout>
      {completed ? (
        <section className="login-card invite-complete-card">
          <CheckCircle2 aria-hidden="true" size={34} />
          <div>
            <h1>Acesso ativado</h1>
            <p>Sua senha foi definida e sua sessão já está protegida.</p>
          </div>
          <button onClick={() => window.location.assign("/")} type="button">
            Entrar no painel
          </button>
        </section>
      ) : (
        <form className="login-card" onSubmit={submit}>
          <div>
            <h1>Defina sua senha</h1>
            <p>O link é individual e deixará de funcionar depois do uso.</p>
          </div>
          <label>
            Nova senha
            <PasswordInput autoComplete="new-password" minLength={12} onChange={setPassword} value={password} />
          </label>
          {error ? <div className="error-box">{error}</div> : null}
          <button disabled={loading || !token} type="submit">
            {loading ? "Ativando..." : "Ativar acesso"}
          </button>
        </form>
      )}
    </AuthLayout>
  );
}
