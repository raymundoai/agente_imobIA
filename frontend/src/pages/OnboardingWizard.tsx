import { useState } from "react";
import { ArrowRight, Bot, Building2, CheckCircle2, Clock, Hexagon, MessageCircle, Sparkles } from "lucide-react";
import { request } from "../api/client";
import type { BusinessHours, Tenant, TenantSettings } from "../api/types";
import { formatDocument } from "../lib/format";
import { isValidBrazilianDocument } from "../lib/settingsValidation";
import { defaultBusinessHours } from "./settings/TenantSettingsPanel";

type Step = "company" | "hours" | "agent" | "channels" | "done";
type Profile = NonNullable<TenantSettings["profile"]>;

const steps: Array<{ key: Step; label: string; icon: typeof Building2 }> = [
  { key: "company", label: "Empresa", icon: Building2 },
  { key: "hours", label: "Atendimento", icon: Clock },
  { key: "agent", label: "Agente de IA", icon: Bot },
  { key: "channels", label: "Canais", icon: MessageCircle },
  { key: "done", label: "Pronto", icon: Sparkles },
];
const weekdayKeys = ["monday", "tuesday", "wednesday", "thursday", "friday"] as const;
const voiceTones = [
  { value: "friendly", label: "Amigável" },
  { value: "professional", label: "Profissional" },
  { value: "consultative", label: "Consultivo" },
  { value: "informal", label: "Descontraído" },
];
const emojiOptions = [
  { value: "low", label: "Poucos emojis" },
  { value: "none", label: "Sem emojis" },
  { value: "moderate", label: "Emojis moderados" },
];

export function OnboardingWizard({
  tenant: initialTenant,
  token,
  trialEndsAt,
  onFinished,
}: {
  tenant: Tenant;
  token: string | null;
  trialEndsAt: string | null;
  onFinished: (tenant: Tenant, destination?: string) => void;
}) {
  const [tenant, setTenant] = useState(initialTenant);
  const [step, setStep] = useState<Step>("company");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savedProfile = initialTenant.settings.profile ?? {};
  const [company, setCompany] = useState({
    display_name: savedProfile.display_name ?? initialTenant.name,
    legal_name: savedProfile.legal_name ?? "",
    document_type: savedProfile.document_type ?? ("cnpj" as "cpf" | "cnpj"),
    document_number: formatDocument(savedProfile.document_number ?? "", savedProfile.document_type ?? "cnpj"),
  });
  const savedHours = typeof savedProfile.business_hours === "object" ? savedProfile.business_hours : null;
  const [hours, setHours] = useState({
    start: savedHours?.days.monday.start ?? "08:30",
    end: savedHours?.days.monday.end ?? "18:00",
    saturday: savedHours?.days.saturday.enabled ?? false,
    saturday_start: savedHours?.days.saturday.start ?? "09:00",
    saturday_end: savedHours?.days.saturday.end ?? "13:00",
    regions: savedProfile.regions ?? "",
  });
  const savedAgent = ((initialTenant.settings.agents ?? {}) as { leads?: Record<string, string> }).leads ?? {};
  const [agent, setAgent] = useState({
    name: savedAgent.name ?? "Agente de Leads",
    voice_tone: savedAgent.voice_tone ?? "friendly",
    emoji_usage: savedAgent.emoji_usage ?? "low",
  });
  const stepIndex = steps.findIndex((item) => item.key === step);

  function next() {
    setError(null);
    setStep(steps[Math.min(stepIndex + 1, steps.length - 1)].key);
  }

  async function saveProfile(patch: Partial<Profile>) {
    const { voice_tone: _legacy, ...current } = tenant.settings.profile ?? {};
    const updated = await request<Tenant>(
      `/tenants/${tenant.id}/settings/profile`,
      { method: "PATCH", body: JSON.stringify({ profile: { ...current, ...patch } }) },
      token,
    );
    setTenant(updated);
  }

  async function run(action: () => Promise<void>) {
    setSaving(true);
    setError(null);
    try {
      await action();
      next();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  }

  function saveCompany() {
    const digits = company.document_number.replace(/\D/g, "");
    if (company.display_name.trim().length < 2) return setError("Informe o nome da imobiliária.");
    if (digits && !isValidBrazilianDocument(digits, company.document_type)) {
      return setError(`Informe um ${company.document_type.toUpperCase()} válido ou deixe em branco.`);
    }
    void run(() =>
      saveProfile({
        display_name: company.display_name.trim(),
        legal_name: company.legal_name.trim() || undefined,
        document_type: digits ? company.document_type : undefined,
        document_number: digits || undefined,
      }),
    );
  }

  function saveHours() {
    if (hours.start >= hours.end) return setError("O início do atendimento deve ser antes do fim.");
    if (hours.saturday && hours.saturday_start >= hours.saturday_end) {
      return setError("No sábado, o início deve ser antes do fim.");
    }
    const business: BusinessHours = defaultBusinessHours();
    for (const key of weekdayKeys) {
      business.days[key] = { ...business.days[key], enabled: true, start: hours.start, end: hours.end };
    }
    business.days.saturday = {
      ...business.days.saturday,
      enabled: hours.saturday,
      start: hours.saturday_start,
      end: hours.saturday_end,
    };
    void run(() => saveProfile({ business_hours: business, regions: hours.regions.trim() || undefined }));
  }

  function saveAgent() {
    if (agent.name.trim().length < 2) return setError("Dê um nome ao agente.");
    void run(async () => {
      const updated = await request<Tenant>(
        `/tenants/${tenant.id}/settings/agents`,
        {
          method: "PATCH",
          body: JSON.stringify({ agents: { leads: { ...savedAgent, ...agent, name: agent.name.trim() } } }),
        },
        token,
      );
      setTenant(updated);
    });
  }

  async function finish(status: "completed" | "skipped", destination?: string) {
    setSaving(true);
    setError(null);
    try {
      const updated = await request<Tenant>(
        `/tenants/${tenant.id}/onboarding`,
        { method: "PATCH", body: JSON.stringify({ status }) },
        token,
      );
      onFinished(updated, destination);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível concluir.");
      setSaving(false);
    }
  }

  const trialDays = trialEndsAt ? Math.max(0, Math.ceil((new Date(trialEndsAt).getTime() - Date.now()) / 86_400_000)) : null;

  return (
    <main className="onboarding-page">
      <header className="onboarding-header">
        <div className="onboarding-brand">
          <span className="login-logo"><Hexagon size={20} strokeWidth={2.4} /></span>
          <strong>ImmobIA</strong>
        </div>
        {step !== "done" ? (
          <button className="link-button" disabled={saving} onClick={() => void finish("skipped")} type="button">
            Configurar depois
          </button>
        ) : null}
      </header>

      <ol className="onboarding-steps" aria-label="Etapas da configuração">
        {steps.map((item, index) => {
          const Icon = item.icon;
          const state = index < stepIndex ? "done" : index === stepIndex ? "current" : "todo";
          return (
            <li aria-current={state === "current" ? "step" : undefined} className={`onboarding-step ${state}`} key={item.key}>
              <span>{state === "done" ? <CheckCircle2 size={16} /> : <Icon size={16} />}</span>
              {item.label}
            </li>
          );
        })}
      </ol>

      <section className="onboarding-card">
        {step === "company" ? (
          <>
            <StepTitle title="Conte sobre a sua imobiliária" text="Esses dados aparecem para a equipe e são usados na cobrança. CPF ou CNPJ pode ficar para depois." />
            <div className="form-grid">
              <label>
                Nome da imobiliária
                <input value={company.display_name} onChange={(event) => setCompany({ ...company, display_name: event.target.value })} />
              </label>
              <label>
                Razão social
                <input placeholder="Opcional" value={company.legal_name} onChange={(event) => setCompany({ ...company, legal_name: event.target.value })} />
              </label>
              <label>
                Documento
                <select
                  value={company.document_type}
                  onChange={(event) => {
                    const type = event.target.value as "cpf" | "cnpj";
                    setCompany({ ...company, document_type: type, document_number: formatDocument(company.document_number, type) });
                  }}
                >
                  <option value="cnpj">CNPJ</option>
                  <option value="cpf">CPF</option>
                </select>
              </label>
              <label>
                Número
                <input
                  inputMode="numeric"
                  placeholder="Opcional"
                  value={company.document_number}
                  onChange={(event) => setCompany({ ...company, document_number: formatDocument(event.target.value, company.document_type) })}
                />
              </label>
            </div>
          </>
        ) : null}

        {step === "hours" ? (
          <>
            <StepTitle title="Quando vocês atendem?" text="O agente usa esse horário para avisar quando um corretor poderá responder. Ajuste dia a dia depois em Configurações." />
            <div className="form-grid">
              <label>
                Segunda a sexta, das
                <input type="time" value={hours.start} onChange={(event) => setHours({ ...hours, start: event.target.value })} />
              </label>
              <label>
                até
                <input type="time" value={hours.end} onChange={(event) => setHours({ ...hours, end: event.target.value })} />
              </label>
            </div>
            <label className="checkbox-row">
              <input checked={hours.saturday} type="checkbox" onChange={(event) => setHours({ ...hours, saturday: event.target.checked })} />
              Também atendemos aos sábados
            </label>
            {hours.saturday ? (
              <div className="form-grid">
                <label>
                  Sábado, das
                  <input type="time" value={hours.saturday_start} onChange={(event) => setHours({ ...hours, saturday_start: event.target.value })} />
                </label>
                <label>
                  até
                  <input type="time" value={hours.saturday_end} onChange={(event) => setHours({ ...hours, saturday_end: event.target.value })} />
                </label>
              </div>
            ) : null}
            <label>
              Regiões de atuação
              <textarea
                placeholder="Ex.: Zona Sul de Porto Alegre, Canoas, Novo Hamburgo"
                rows={3}
                value={hours.regions}
                onChange={(event) => setHours({ ...hours, regions: event.target.value })}
              />
            </label>
          </>
        ) : null}

        {step === "agent" ? (
          <>
            <StepTitle title="Personalize o agente de IA" text="É ele quem recebe os leads no WhatsApp e no Telegram. Regras de transferência e restrições ficam em Configurações > Configuração da IA." />
            <div className="form-grid">
              <label>
                Nome do agente
                <input value={agent.name} onChange={(event) => setAgent({ ...agent, name: event.target.value })} />
              </label>
              <label>
                Tom de voz
                <select value={agent.voice_tone} onChange={(event) => setAgent({ ...agent, voice_tone: event.target.value })}>
                  {voiceTones.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                Uso de emojis
                <select value={agent.emoji_usage} onChange={(event) => setAgent({ ...agent, emoji_usage: event.target.value })}>
                  {emojiOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>
          </>
        ) : null}

        {step === "channels" ? (
          <>
            <StepTitle title="Conecte seus canais" text="Para o agente atender, conecte o WhatsApp da imobiliária lendo um QR Code. Leva cerca de um minuto." />
            <div className="onboarding-choice">
              <button className="primary-button" disabled={saving} onClick={() => void finish("completed", "/configuracoes?aba=channels")} type="button">
                <MessageCircle size={16} />
                Conectar WhatsApp agora
              </button>
              <p>Você também pode conectar o Telegram na mesma tela.</p>
            </div>
          </>
        ) : null}

        {step === "done" ? (
          <>
            <StepTitle
              title="Tudo pronto para começar"
              text={
                trialDays !== null
                  ? `Seu teste grátis vai até ${new Date(trialEndsAt as string).toLocaleDateString("pt-BR")} (${trialDays} dia${trialDays === 1 ? "" : "s"}). Escolha um plano quando quiser, sem perder o que já configurou.`
                  : "Sua conta está configurada."
              }
            />
            <div className="onboarding-choice">
              <button className="primary-button" disabled={saving} onClick={() => void finish("completed")} type="button">
                Ir para o painel
                <ArrowRight size={16} />
              </button>
              <button className="secondary-button" disabled={saving} onClick={() => void finish("completed", "/configuracoes?aba=billing")} type="button">
                Ver planos
              </button>
            </div>
          </>
        ) : null}

        {error ? <div className="error-box">{error}</div> : null}

        {step === "company" || step === "hours" || step === "agent" ? (
          <footer className="onboarding-actions">
            <button className="link-button" disabled={saving} onClick={next} type="button">Pular etapa</button>
            <button
              className="primary-button"
              disabled={saving}
              onClick={step === "company" ? saveCompany : step === "hours" ? saveHours : saveAgent}
              type="button"
            >
              {saving ? "Salvando..." : "Salvar e continuar"}
              {!saving ? <ArrowRight size={16} /> : null}
            </button>
          </footer>
        ) : null}
        {step === "channels" ? (
          <footer className="onboarding-actions">
            <span />
            <button className="link-button" disabled={saving} onClick={next} type="button">Conectar depois</button>
          </footer>
        ) : null}
      </section>
    </main>
  );
}

function StepTitle({ title, text }: { title: string; text: string }) {
  return (
    <div className="onboarding-title">
      <h1>{title}</h1>
      <p>{text}</p>
    </div>
  );
}
