import { FormEvent, useState } from "react";
import { ArrowLeft, ArrowRight, Building2 } from "lucide-react";
import type { CompanyOption } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AuthLayout } from "../components/AuthLayout";
import { PasswordInput } from "../components/PasswordInput";

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
    <AuthLayout>
      {companies ? (
        <section className="login-card" aria-labelledby="company-choice-title">
          <div>
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
            <h1>Entrar</h1>
            <p>Use o email e a senha da sua conta.</p>
          </div>
          <label>
            Email
            <input autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
          </label>
          <label>
            Senha
            <PasswordInput autoComplete="current-password" onChange={setPassword} value={password} />
          </label>
          {error ? <div className="error-box">{error}</div> : null}
          <button disabled={loading} type="submit">
            {loading ? "Entrando..." : "Entrar"}
          </button>
          <a className="login-switch" href="/criar-conta">
            Ainda não tem conta? <strong>Criar conta</strong>
          </a>
        </form>
      )}
    </AuthLayout>
  );
}
