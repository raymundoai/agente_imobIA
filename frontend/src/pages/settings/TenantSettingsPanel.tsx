import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type {
  BusinessDaySchedule,
  BusinessHours,
  BusinessWeekday,
  Tenant,
  TenantSettings,
  User,
} from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import {
  type BusinessIdentity,
  BusinessIdentityFields,
  identityFromProfile,
  identityToProfile,
  validateIdentity,
} from "../../components/BusinessIdentityFields";
import { Card } from "../../components/Card";

type TenantProfileForm = {
  display_name: string;
  identity: BusinessIdentity;
  business_hours: BusinessHours;
  regions: string;
};

export const weekdays: Array<{ key: BusinessWeekday; label: string }> = [
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

export function defaultBusinessHours(): BusinessHours {
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
  const [personName, setPersonName] = useState("");
  const [form, setForm] = useState<TenantProfileForm>({
    display_name: "",
    identity: identityFromProfile({}, ""),
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
    request<User>("/users/me", {}, token).then((user) => setPersonName(user.name)).catch(() => undefined);
  }, [token]);

  useEffect(() => {
    const profile = tenant?.settings.profile ?? {};
    const nextForm: TenantProfileForm = {
      display_name: profile.display_name ?? tenant?.name ?? "",
      identity: identityFromProfile(profile, profile.document_type === "cnpj" ? "" : personName),
      business_hours: normalizedBusinessHours(profile.business_hours),
      regions: profile.regions ?? "",
    };
    setForm(nextForm);
    setInitialForm(nextForm);
  }, [tenant, personName]);

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
      const {
        legal_name: _name,
        document_type: _type,
        document_number: _number,
        business_type: _business,
        ...kept
      } = currentProfile;
      const profile: NonNullable<TenantSettings["profile"]> = {
        ...kept,
        display_name: form.display_name.trim(),
        business_hours: form.business_hours,
        regions: form.regions,
        ...identityToProfile(form.identity),
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
          <p>Quem você é, onde atua e quando atende. O agente de IA usa tudo isso nas conversas.</p>
        </div>
        {canManage ? null : <span className="settings-status">Somente leitura</span>}
      </div>

      <fieldset className="settings-form-fieldset" disabled={!canManage}>
      <BusinessIdentityFields onChange={(identity) => setForm((current) => ({ ...current, identity }))} value={form.identity} />
      <div className="form-grid settings-identity-extra">
        <label>
          {form.identity.business_type === "broker" ? "Nome profissional" : "Nome da imobiliária"}
          <input value={form.display_name} onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))} placeholder="Como aparece para os leads e a equipe" />
          <small className="field-hint">O agente de IA se apresenta em nome dele.</small>
        </label>
        <label>
          Regiões de atuação
          <input value={form.regions} onChange={(event) => setForm((current) => ({ ...current, regions: event.target.value }))} placeholder="Novo Hamburgo, São Leopoldo, Campo Bom" />
          <small className="field-hint">Texto livre usado pelo agente para entender onde vocês atuam.</small>
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
                  <option value="no">Não</option>
                  <option value="yes">Sim</option>
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

function validateProfile(form: TenantProfileForm): string | null {
  if (form.display_name.trim().length < 2) return "Informe o nome exibido.";
  const identityError = validateIdentity(form.identity);
  if (identityError) return identityError;
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
