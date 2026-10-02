import { FormEvent, useState } from "react";
import { ArrowLeft, ArrowRight, Building2, Hexagon } from "lucide-react";
import type { CompanyOption } from "../api/types";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [companies, setCompanies] = useState<CompanyOption[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function enter(tenantSlug?: string) {
    setLoading(true);
    setError(null);
    try {
      const choices = await login(email, password, tenantSlug);
      setCompanies(choices);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no login");
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void enter();
  }

  return (
    <main className="login-page">
      <div className="login-glow" />
      <div className="login-heading">
        <div className="login-logo">
          <Hexagon size={28} strokeWidth={2.4} />
        </div>
        <h1>ImmobIA</h1>
        <p>O sistema operacional da sua imobiliária</p>
      </div>
      {companies ? (
        <section className="login-card" aria-labelledby="company-choice-title">
          <div>
            <span className="eyebrow">ImmobIA</span>
            <h1 id="company-choice-title">Escolha a empresa</h1>
            <p>Seu email tem acesso a mais de uma imobiliária.</p>
          </div>
          <div className="company-choices">
            {companies.map((company) => (
              <button className="company-choice" disabled={loading} key={company.slug} onClick={() => void enter(company.slug)} type="button">
                <Building2 size={18} />
                <span>{company.name}</span>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
          {error ? <div className="error-box">{error}</div> : null}
          <button className="login-switch" onClick={() => setCompanies(null)} type="button">
            <ArrowLeft size={14} />
            Voltar
          </button>
        </section>
      ) : (
        <form className="login-card" onSubmit={submit}>
          <div>
            <span className="eyebrow">ImmobIA</span>
            <h1>Acesse o painel</h1>
            <p>Informe seu email e senha.</p>
          </div>
          <label>
            Email
            <input autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
          </label>
          <label>
            Senha
            <input
              autoComplete="current-password"
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
          <a className="login-switch" href="/criar-conta">
            Ainda não tem conta? <strong>Criar conta grátis</strong>
          </a>
        </form>
      )}
      <p className="login-footnote">Acesso restrito a corretores e gestores credenciados</p>
    </main>
  );
}
