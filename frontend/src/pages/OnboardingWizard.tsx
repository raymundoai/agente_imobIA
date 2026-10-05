import { useEffect, useState } from "react";
import { Bot, Building2, CheckCircle2, Clock, MessageCircle, Sparkles } from "lucide-react";
import { request } from "../api/client";
import type { BusinessHours, Tenant, TenantSettings, User } from "../api/types";
import {
  type BusinessIdentity,
  BusinessIdentityFields,
  identityFromProfile,
  identityToProfile,
  validateIdentity,
} from "../components/BusinessIdentityFields";
import { useWhatsappConnection, WhatsappConnectModal } from "../components/WhatsappConnect";
import { DEFAULT_AGENT_NAME, EMOJI_LEVELS, VOICE_TONES } from "../lib/agentOptions";
import { formatPhone } from "../lib/format";
import { defaultBusinessHours } from "./settings/TenantSettingsPanel";
import { BrandMark } from "../components/BrandMark";

type Step = "company" | "hours" | "agent" | "channels" | "done";
type Profile = NonNullable<TenantSettings["profile"]>;

const steps: Array<{ key: Step; label: string; icon: typeof Building2 }> = [
  { key: "company", label: "Perfil", icon: Building2 },
  { key: "hours", label: "Atendimento", icon: Clock },
  { key: "agent", label: "Agente de IA", icon: Bot },
  { key: "channels", label: "WhatsApp", icon: MessageCircle },
  { key: "done", label: "Pronto", icon: Sparkles },
];
const weekdayKeys = ["monday", "tuesday", "wednesday", "thursday", "friday"] as const;

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
  const businessName = savedProfile.display_name ?? initialTenant.name;
  const [identity, setIdentity] = useState<BusinessIdentity>(() => identityFromProfile(savedProfile, ""));
  const whatsapp = useWhatsappConnection(token);

  // The signup already asked for the person's name; use it as the CPF holder by default.
  useEffect(() => {
    request<User>("/users/me", {}, token)
      .then((user) => setIdentity((current) => (current.cpf_name ? current : { ...current, cpf_name: user.name })))
      .catch(() => undefined);
  }, [token]);
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
    name: savedAgent.name && savedAgent.name !== DEFAULT_AGENT_NAME ? savedAgent.name : "",
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
    if (!identity.business_type) return setError("Escolha se você é corretor autônomo ou imobiliária.");
    const invalid = validateIdentity(identity);
    if (invalid) return setError(invalid);
    void run(() => saveProfile(identityToProfile(identity)));
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
    void run(async () => {
      const updated = await request<Tenant>(
        `/tenants/${tenant.id}/settings/agents`,
        {
          method: "PATCH",
          body: JSON.stringify({ agents: { leads: { ...savedAgent, ...agent, name: agent.name.trim() || DEFAULT_AGENT_NAME } } }),
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
          <span className="brand-icon"><BrandMark /></span>
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

      <section className="onboarding-card" key={step}>
        {step === "company" ? (
          <>
            <StepTitle title="Como você trabalha?" text="Isso ajuda o agente a se apresentar do jeito certo. O documento é usado na cobrança e pode ficar para depois." />
            <BusinessIdentityFields onChange={setIdentity} value={identity} />
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
              <span>Regiões de atuação <span className="optional">(opcional)</span></span>
              <textarea
                placeholder="Ex.: Zona Sul de Porto Alegre, Canoas, Novo Hamburgo"
                rows={3}
                value={hours.regions}
                onChange={(event) => setHours({ ...hours, regions: event.target.value })}
              />
              <small className="field-hint">Escreva do seu jeito. O agente usa isso para entender onde você atua e avisar o lead quando ele procura fora dessas regiões.</small>
            </label>
          </>
        ) : null}

        {step === "agent" ? (
          <>
            <StepTitle title="Personalize o agente de IA" text="É ele quem responde os leads no WhatsApp. Regras de transferência e o que ele deve saber ficam em Configurações > Agente de IA." />
            <div className="form-grid">
              <label>
                <span>Nome do agente <span className="optional">(opcional)</span></span>
                <input placeholder="Ex.: Sofia" value={agent.name} onChange={(event) => setAgent({ ...agent, name: event.target.value })} />
              </label>
              <label>
                Tom de voz
                <select value={agent.voice_tone} onChange={(event) => setAgent({ ...agent, voice_tone: event.target.value })}>
                  {VOICE_TONES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                Quantidade de emojis
                <select value={agent.emoji_usage} onChange={(event) => setAgent({ ...agent, emoji_usage: event.target.value })}>
                  {EMOJI_LEVELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>
            <AgentPreview
              businessName={businessName}
              businessType={identity.business_type}
              emoji={agent.emoji_usage}
              name={agent.name.trim()}
            />
          </>
        ) : null}

        {step === "channels" ? (
          <>
            <StepTitle
              title={whatsapp.connected ? "WhatsApp conectado" : "Conecte o WhatsApp"}
              text={
                whatsapp.connected
                  ? "Pronto: as mensagens desse número já chegam ao agente."
                  : "O agente atende pelo WhatsApp da imobiliária. Basta ler um QR Code com o celular; leva cerca de um minuto."
              }
            />
            {whatsapp.connected ? (
              <div className="onboarding-connected">
                <CheckCircle2 size={22} />
                <strong>{formatPhone(whatsapp.connection?.connected_phone) || whatsapp.connection?.connected_name || "Número conectado"}</strong>
              </div>
            ) : (
              <div className="onboarding-choice">
                <button className="primary-button" disabled={saving} onClick={() => void whatsapp.connect()} type="button">
                  <MessageCircle size={16} />
                  Mostrar QR Code
                </button>
              </div>
            )}
            {whatsapp.modalOpen ? <WhatsappConnectModal whatsapp={whatsapp} /> : null}
          </>
        ) : null}

        {step === "done" ? (
          <>
            {trialDays !== null ? (
              <StepTitle
                title="Tudo pronto para começar"
                text={`Seu teste grátis vai até ${new Date(trialEndsAt as string).toLocaleDateString("pt-BR")} (${trialDays} dia${trialDays === 1 ? "" : "s"}). Escolha um plano quando quiser, sem perder o que já configurou.`}
              />
            ) : (
              <StepTitle
                title="Falta só escolher o plano"
                text="Sua conta está configurada. O agente começa a atender assim que a primeira mensalidade for paga."
              />
            )}
            <div className="onboarding-choice">
              {trialDays !== null ? (
                <>
                  <button className="primary-button" disabled={saving} onClick={() => void finish("completed")} type="button">
                    Ir para o painel
                  </button>
                  <button className="secondary-button" disabled={saving} onClick={() => void finish("completed", "/configuracoes?aba=billing")} type="button">
                    Ver planos
                  </button>
                </>
              ) : (
                <>
                  <button className="primary-button" disabled={saving} onClick={() => void finish("completed", "/configuracoes?aba=billing")} type="button">
                    Escolher plano
                  </button>
                  <button className="secondary-button" disabled={saving} onClick={() => void finish("completed")} type="button">
                    Ir para o painel
                  </button>
                </>
              )}
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
            </button>
          </footer>
        ) : null}
        {step === "channels" ? (
          <footer className="onboarding-actions">
            <span />
            {whatsapp.connected ? (
              <button className="primary-button" onClick={next} type="button">Continuar</button>
            ) : (
              <button className="link-button" disabled={saving} onClick={next} type="button">Conectar depois</button>
            )}
          </footer>
        ) : null}
      </section>
    </main>
  );
}

const EMOJI_SAMPLE: Record<string, string> = { none: "", low: " 🙂", moderate: " 😊🏡" };

/** What the lead sees first, so the name and tone choices are concrete. */
function AgentPreview({
  name,
  businessName,
  businessType,
  emoji,
}: {
  name: string;
  businessName: string;
  businessType: "broker" | "agency" | null;
  emoji: string;
}) {
  const owner = businessType === "broker" ? `do corretor ${businessName}` : `da ${businessName}`;
  const intro = name ? `Oi! Eu sou ${name}, assistente virtual ${owner}.` : `Oi! Sou o assistente virtual ${owner}.`;
  return (
    <div className="agent-preview" aria-label="Prévia da primeira mensagem">
      <span className="agent-preview-label">Assim o agente se apresenta</span>
      <p className="agent-preview-bubble">
        {intro} Está procurando imóvel para comprar ou alugar?{EMOJI_SAMPLE[emoji] ?? ""}
      </p>
    </div>
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
