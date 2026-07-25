import { FormEvent, useState } from "react";
import { ArrowRight, Hexagon } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(tenantSlug, email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no login");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-glow" />
      <div className="login-heading">
        <div className="login-logo">
          <Hexagon size={28} strokeWidth={2.4} />
        </div>
        <h1>ImobIA</h1>
        <p>O sistema operacional da sua imobiliária</p>
      </div>
      <form className="login-card" onSubmit={submit}>
        <div>
          <span className="eyebrow">ImobIA</span>
          <h1>Acesse o painel</h1>
          <p>Informe sua empresa, email e senha.</p>
        </div>
        <label>
          Empresa
          <input value={tenantSlug} onChange={(event) => setTenantSlug(event.target.value)} />
        </label>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
        </label>
        <label>
          Senha
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
          />
        </label>
        {error ? <div className="error-box">{error}</div> : null}
        <button disabled={loading} type="submit">
          {loading ? "Entrando..." : "Entrar"}
          {!loading ? <ArrowRight size={16} /> : null}
        </button>
      </form>
      <p className="login-footnote">Acesso restrito a corretores e gestores credenciados</p>
    </main>
  );
}
