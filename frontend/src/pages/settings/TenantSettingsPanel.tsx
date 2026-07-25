import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { Tenant, TenantSettings } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Card } from "../../components/Card";

type TenantProfileForm = {
  display_name: string;
  business_hours: string;
  regions: string;
  voice_tone: string;
};

const emptyProfile: TenantProfileForm = {
  display_name: "",
  business_hours: "",
  regions: "",
  voice_tone: "",
};

export function TenantSettingsPanel({
  tenant,
  onTenantChange,
}: {
  tenant: Tenant | null;
  onTenantChange: (tenant: Tenant) => void;
}) {
  const { token } = useAuth();
  const claims = getTokenClaims(token);
  const [form, setForm] = useState<TenantProfileForm>(emptyProfile);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const profile = tenant?.settings.profile ?? {};
    setForm({
      display_name: profile.display_name ?? tenant?.name ?? "",
      business_hours: profile.business_hours ?? "",
      regions: profile.regions ?? "",
      voice_tone: profile.voice_tone ?? "",
    });
  }, [tenant]);

  async function save() {
    if (!claims || !tenant) {
      setMessage("Empresa não identificada no acesso atual.");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const settings: TenantSettings = {
        ...tenant.settings,
        profile: {
          ...tenant.settings.profile,
          ...form,
        },
      };
      const updated = await request<Tenant>(
        `/tenants/${claims.tenantId}/settings`,
        {
          method: "PATCH",
          body: JSON.stringify({ settings }),
        },
        token,
      );
      onTenantChange(updated);
      setMessage("Configurações da empresa salvas.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao salvar empresa.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Empresa</h2>
          <p>Dados usados pela equipe e pela IA no atendimento aos clientes.</p>
        </div>
        <span className="settings-status">Empresa</span>
      </div>

      <div className="form-grid">
        <label>
          Nome exibido
          <input
            value={form.display_name}
            onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))}
            placeholder="Eugênia Imóveis"
          />
        </label>
        <label>
          Horário de atendimento
          <input
            value={form.business_hours}
            onChange={(event) =>
              setForm((current) => ({ ...current, business_hours: event.target.value }))
            }
            placeholder="Seg-Sex 08:30-18:00"
          />
        </label>
        <label>
          Regiões atendidas
          <input
            value={form.regions}
            onChange={(event) => setForm((current) => ({ ...current, regions: event.target.value }))}
            placeholder="Novo Hamburgo, São Leopoldo, Campo Bom"
          />
        </label>
        <label className="form-span-2">
          Tom de voz
          <textarea
            value={form.voice_tone}
            onChange={(event) => setForm((current) => ({ ...current, voice_tone: event.target.value }))}
            placeholder="Profissional, direto, cordial e orientado à conversão."
          />
        </label>
      </div>

      <div className="settings-actions">
        {message ? <span>{message}</span> : null}
        <button disabled={saving || !tenant} onClick={save} type="button">
          {saving ? "Salvando..." : "Salvar empresa"}
        </button>
      </div>
    </Card>
  );
}
