import { FormEvent, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { request } from "../api/client";
import type { SignupResponse } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AuthLayout } from "../components/AuthLayout";
import { PasswordInput } from "../components/PasswordInput";

type SignupForm = {
  company_name: string;
  admin_name: string;
  email: string;
  password: string;
};

const emptyForm: SignupForm = {
  company_name: "",
  admin_name: "",
  email: "",
  password: "",
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
      const result = await request<SignupResponse>("/signup", {
        method: "POST",
        body: JSON.stringify(form),
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
    <AuthLayout>
      <form className="login-card signup-card" onSubmit={submit}>
        <div>
          <h1>Criar conta</h1>
          <p>Depois do cadastro, você configura a imobiliária em poucos passos e escolhe o plano.</p>
        </div>
        <label>
          Seu nome
          <input autoComplete="name" value={form.admin_name} onChange={(event) => update("admin_name", event.target.value)} />
        </label>
        <label>
          Nome da imobiliária ou nome profissional
          <input autoComplete="organization" placeholder="Ex.: Eugênia Imóveis ou Pedro Corretor" value={form.company_name} onChange={(event) => update("company_name", event.target.value)} />
          <small className="field-hint">É como o agente de IA vai se apresentar aos leads.</small>
        </label>
        <label>
          Email
          <input autoComplete="email" type="email" value={form.email} onChange={(event) => update("email", event.target.value)} />
        </label>
        <label>
          Senha
          <PasswordInput autoComplete="new-password" minLength={12} onChange={(value) => update("password", value)} value={form.password} />
        </label>
        {error ? <div className="error-box">{error}</div> : null}
        <button disabled={loading} type="submit">
          {loading ? "Criando conta..." : "Criar conta e começar"}
        </button>
        <a className="login-switch" href="/">
          <ArrowLeft size={14} />
          Já tenho conta
        </a>
      </form>
    </AuthLayout>
  );
}

function validate(form: SignupForm): string | null {
  if (form.admin_name.trim().length < 2) return "Informe seu nome.";
  if (form.company_name.trim().length < 2) return "Informe o nome da imobiliária ou seu nome profissional.";
  if (!form.email.includes("@")) return "Informe um email válido.";
  if (form.password.length < 12) return "A senha precisa ter ao menos 12 caracteres.";
  return null;
}
