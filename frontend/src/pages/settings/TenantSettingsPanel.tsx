import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type {
  BusinessDaySchedule,
  BusinessHours,
  BusinessWeekday,
  Tenant,
  TenantSettings,
} from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Card } from "../../components/Card";
import { isValidBrazilianDocument } from "../../lib/settingsValidation";

type TenantProfileForm = {
  display_name: string;
  legal_name: string;
  document_type: "cpf" | "cnpj";
  document_number: string;
  business_hours: BusinessHours;
  regions: string;
};

const weekdays: Array<{ key: BusinessWeekday; label: string }> = [
  { key: "monday", label: "Segunda-feira" },
  { key: "tuesday", label: "Terça-feira" },
  { key: "wednesday", label: "Quarta-feira" },
  { key: "thursday", label: "Quinta-feira" },
  { key: "friday", label: "Sexta-feira" },
  { key: "saturday", label: "Sábado" },
  { key: "sunday", label: "Domingo" },
];

function day(enabled: boolean): BusinessDaySchedule {
  return {
    enabled,
    start: "08:30",
    end: "18:00",
    break_enabled: false,
    break_start: "12:00",
    break_end: "13:00",
  };
}

function defaultBusinessHours(): BusinessHours {
  return {
    timezone: "America/Sao_Paulo",
    days: {
      monday: day(true),
      tuesday: day(true),
      wednesday: day(true),
      thursday: day(true),
      friday: day(true),
      saturday: day(false),
      sunday: day(false),
    },
  };
}

function normalizedBusinessHours(value: unknown): BusinessHours {
  if (!value || typeof value !== "object" || !("days" in value)) return defaultBusinessHours();
  const saved = value as Partial<BusinessHours>;
  const defaults = defaultBusinessHours();
  return {
    timezone: saved.timezone || defaults.timezone,
    days: Object.fromEntries(
      weekdays.map(({ key }) => [key, { ...defaults.days[key], ...(saved.days?.[key] ?? {}) }]),
    ) as BusinessHours["days"],
  };
}

export function TenantSettingsPanel({
  tenant,
  onTenantChange,
  onDirtyChange,
}: {
  tenant: Tenant | null;
  onTenantChange: (tenant: Tenant) => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { token } = useAuth();
  const claims = getTokenClaims(token);
  const [form, setForm] = useState<TenantProfileForm>({
    display_name: "",
    legal_name: "",
    document_type: "cnpj",
    document_number: "",
    business_hours: defaultBusinessHours(),
    regions: "",
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error">("success");
  const [initialForm, setInitialForm] = useState<TenantProfileForm | null>(null);
  const canManage = claims?.role === "admin";
  const dirty = initialForm !== null && JSON.stringify(form) !== JSON.stringify(initialForm);

  useEffect(() => {
    const profile = tenant?.settings.profile ?? {};
    const nextForm: TenantProfileForm = {
      display_name: profile.display_name ?? tenant?.name ?? "",
      legal_name: profile.legal_name ?? "",
      document_type: profile.document_type ?? "cnpj",
      document_number: formatDocument(profile.document_number ?? "", profile.document_type ?? "cnpj"),
      business_hours: normalizedBusinessHours(profile.business_hours),
      regions: profile.regions ?? "",
    };
    setForm(nextForm);
    setInitialForm(nextForm);
  }, [tenant]);

  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  function updateDay(key: BusinessWeekday, patch: Partial<BusinessDaySchedule>) {
    setForm((current) => ({
      ...current,
      business_hours: {
        ...current.business_hours,
        days: {
          ...current.business_hours.days,
          [key]: { ...current.business_hours.days[key], ...patch },
        },
      },
    }));
  }

  async function save() {
    if (!claims || !tenant) {
      setMessage("Empresa não identificada no acesso atual.");
      setMessageKind("error");
      return;
    }
    const validationError = validateProfile(form);
    if (validationError) {
      setMessage(validationError);
      setMessageKind("error");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const { voice_tone: _legacyVoiceTone, ...currentProfile } = tenant.settings.profile ?? {};
      const profile: NonNullable<TenantSettings["profile"]> = {
        ...currentProfile,
        ...form,
        document_number: form.document_number.replace(/\D/g, ""),
      };
      const updated = await request<Tenant>(
        `/tenants/${claims.tenantId}/settings/profile`,
        { method: "PATCH", body: JSON.stringify({ profile }) },
        token,
      );
      onTenantChange(updated);
      setMessage("Configurações da empresa salvas.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao salvar empresa.");
      setMessageKind("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Empresa</h2>
          <p>Dados institucionais e horários usados pela equipe e pela IA.</p>
        </div>
        <span className="settings-status">{canManage ? "Empresa" : "Somente leitura"}</span>
      </div>

      <fieldset className="settings-form-fieldset" disabled={!canManage}>
      <div className="form-grid">
        <label>
          Nome exibido
          <input value={form.display_name} onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))} placeholder="Eugênia Imóveis" />
        </label>
        <label>
          Nome completo / Razão social
          <input value={form.legal_name} onChange={(event) => setForm((current) => ({ ...current, legal_name: event.target.value }))} placeholder="Eugênia Imóveis Ltda." />
        </label>
        <label>
          Tipo de documento
          <select value={form.document_type} onChange={(event) => {
            const documentType = event.target.value as TenantProfileForm["document_type"];
            setForm((current) => ({ ...current, document_type: documentType, document_number: formatDocument(current.document_number, documentType) }));
          }}>
            <option value="cnpj">CNPJ</option>
            <option value="cpf">CPF</option>
          </select>
        </label>
        <label>
          {form.document_type === "cnpj" ? "CNPJ" : "CPF"}
          <input inputMode="numeric" value={form.document_number} onChange={(event) => setForm((current) => ({ ...current, document_number: formatDocument(event.target.value, current.document_type) }))} placeholder={form.document_type === "cnpj" ? "00.000.000/0000-00" : "000.000.000-00"} />
        </label>
        <label className="form-span-2">
          Regiões atendidas
          <input value={form.regions} onChange={(event) => setForm((current) => ({ ...current, regions: event.target.value }))} placeholder="Novo Hamburgo, São Leopoldo, Campo Bom" />
        </label>
      </div>

      <div className="settings-subsection">
        <div>
          <h3>Horário de atendimento</h3>
          <p>Ative os dias e informe os horários. O intervalo é opcional.</p>
        </div>
        <div className="business-hours-grid">
          {weekdays.map(({ key, label }) => {
            const schedule = form.business_hours.days[key];
            return <div className={schedule.enabled ? "business-day enabled" : "business-day"} key={key}>
              <label className="business-day-toggle">
                <input checked={schedule.enabled} onChange={(event) => updateDay(key, { enabled: event.target.checked })} type="checkbox" />
                <strong>{label}</strong>
              </label>
              <label>Início<input disabled={!schedule.enabled} type="time" value={schedule.start} onChange={(event) => updateDay(key, { start: event.target.value })} /></label>
              <label>Fim<input disabled={!schedule.enabled} type="time" value={schedule.end} onChange={(event) => updateDay(key, { end: event.target.value })} /></label>
              <label className="business-break-toggle">
                <span>Intervalo</span>
                <select disabled={!schedule.enabled} value={schedule.break_enabled ? "yes" : "no"} onChange={(event) => updateDay(key, { break_enabled: event.target.value === "yes" })}>
                  <option value="no">Sem intervalo</option>
                  <option value="yes">Com intervalo</option>
                </select>
              </label>
              {schedule.break_enabled && schedule.enabled ? <>
                <label>Início do intervalo<input type="time" value={schedule.break_start} onChange={(event) => updateDay(key, { break_start: event.target.value })} /></label>
                <label>Fim do intervalo<input type="time" value={schedule.break_end} onChange={(event) => updateDay(key, { break_end: event.target.value })} /></label>
              </> : null}
            </div>;
          })}
        </div>
      </div>
      </fieldset>

      <div className="settings-actions">
        {message ? <span className={`settings-feedback ${messageKind}`} role={messageKind === "error" ? "alert" : "status"} aria-live="polite">{message}</span> : null}
        {dirty ? <span className="unsaved-indicator">Alterações não salvas</span> : null}
        <button disabled={saving || !tenant || !canManage || !dirty} onClick={save} type="button">{saving ? "Salvando..." : "Salvar empresa"}</button>
      </div>
    </Card>
  );
}

function formatDocument(value: string, type: "cpf" | "cnpj") {
  const digits = value.replace(/\D/g, "").slice(0, type === "cnpj" ? 14 : 11);
  if (type === "cpf") return digits.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  return digits.replace(/(\d{2})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1/$2").replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}

function validateProfile(form: TenantProfileForm): string | null {
  const documentDigits = form.document_number.replace(/\D/g, "");
  const expectedDigits = form.document_type === "cnpj" ? 14 : 11;
  if (documentDigits && documentDigits.length !== expectedDigits) {
    return `Informe um ${form.document_type.toUpperCase()} completo.`;
  }
  if (documentDigits && !isValidBrazilianDocument(documentDigits, form.document_type)) {
    return `Informe um ${form.document_type.toUpperCase()} válido.`;
  }
  for (const { key, label } of weekdays) {
    const schedule = form.business_hours.days[key];
    if (!schedule.enabled) continue;
    if (!schedule.start || !schedule.end || schedule.start >= schedule.end) {
      return `Confira os horários de início e fim de ${label.toLowerCase()}.`;
    }
    if (schedule.break_enabled && (
      !schedule.break_start ||
      !schedule.break_end ||
      schedule.break_start >= schedule.break_end ||
      schedule.break_start <= schedule.start ||
      schedule.break_end >= schedule.end
    )) {
      return `O intervalo de ${label.toLowerCase()} deve ficar dentro do horário de atendimento.`;
    }
  }
  return null;
}
