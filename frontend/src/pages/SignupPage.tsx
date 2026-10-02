import { FormEvent, useState } from "react";
import { ArrowLeft, ArrowRight, Hexagon } from "lucide-react";
import { request } from "../api/client";
import type { SignupResponse } from "../api/types";
import { useAuth } from "../auth/AuthContext";

type SignupForm = {
  company_name: string;
  admin_name: string;
  email: string;
  password: string;
  password_confirmation: string;
};

const emptyForm: SignupForm = {
  company_name: "",
  admin_name: "",
  email: "",
  password: "",
  password_confirmation: "",
};

export function SignupPage() {
  const { startSession } = useAuth();
  const [form, setForm] = useState<SignupForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function update<K extends keyof SignupForm>(key: K, value: SignupForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const validation = validate(form);
    if (validation) {
      setError(validation);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { password_confirmation: _confirmation, ...payload } = form;
      const result = await request<SignupResponse>("/signup", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      window.history.replaceState({}, "", "/");
      startSession(result.access_token, result.refresh_token, result.tenant_slug);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível criar a conta.");
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
        <h1>ImmobIA</h1>
        <p>Teste grátis por 7 dias, sem cartão de crédito</p>
      </div>
      <form className="login-card signup-card" onSubmit={submit}>
        <div>
          <span className="eyebrow">Criar conta</span>
          <h1>Comece seu teste grátis</h1>
          <p>Depois do cadastro, você configura a imobiliária em poucos passos.</p>
        </div>
        <label>
          Nome da imobiliária
          <input autoComplete="organization" value={form.company_name} onChange={(event) => update("company_name", event.target.value)} />
        </label>
        <label>
          Seu nome
          <input autoComplete="name" value={form.admin_name} onChange={(event) => update("admin_name", event.target.value)} />
        </label>
        <label>
          Email
          <input autoComplete="email" type="email" value={form.email} onChange={(event) => update("email", event.target.value)} />
        </label>
        <label>
          Senha
          <input autoComplete="new-password" type="password" value={form.password} onChange={(event) => update("password", event.target.value)} />
          <small className="field-hint">Mínimo de 12 caracteres.</small>
        </label>
        <label>
          Confirme a senha
          <input autoComplete="new-password" type="password" value={form.password_confirmation} onChange={(event) => update("password_confirmation", event.target.value)} />
        </label>
        {error ? <div className="error-box">{error}</div> : null}
        <button disabled={loading} type="submit">
          {loading ? "Criando conta..." : "Criar conta e começar"}
          {!loading ? <ArrowRight size={16} /> : null}
        </button>
        <a className="login-switch" href="/">
          <ArrowLeft size={14} />
          Já tenho conta
        </a>
      </form>
    </main>
  );
}

function validate(form: SignupForm): string | null {
  if (form.company_name.trim().length < 2) return "Informe o nome da imobiliária.";
  if (form.admin_name.trim().length < 2) return "Informe seu nome.";
  if (!form.email.includes("@")) return "Informe um email válido.";
  if (form.password.length < 12) return "A senha precisa ter ao menos 12 caracteres.";
  if (form.password !== form.password_confirmation) return "As senhas não conferem.";
  return null;
}
