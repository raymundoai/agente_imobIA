import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { CommercialResourceUsage, CommercialUsage } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable";
import { formatNumber } from "../../lib/format";

export function UsageSettingsPanel() {
  const { token } = useAuth();
  const [usage, setUsage] = useState<CommercialUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadUsage() {
    setLoading(true);
    try {
      setUsage(await request<CommercialUsage>("/usage/commercial", {}, token));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível carregar o uso.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadUsage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (loading && !usage) {
    return <Card className="settings-panel-card"><div className="empty-state" aria-live="polite">Carregando franquias e uso...</div></Card>;
  }

  const visibleResources = (usage?.resources ?? []).filter((item) => (
    item.resource !== "property_search_ai"
    || item.granted > 0
    || item.measured > 0
  ));
  const exhausted = visibleResources.filter((item) => item.available <= 0);

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Plano e uso</h2>
          <p>Acompanhe atendimentos da IA, buscas e otimizações incluídos no ciclo.</p>
        </div>
        <div className="settings-header-actions">
          <span className="settings-status">
            {usage ? `${usage.plan.name} · ${modeLabel(usage.enforcement_mode)}` : "Plano indisponível"}
          </span>
          <button className="button-outline" disabled={loading} onClick={() => void loadUsage()} type="button">
            {loading ? "Atualizando..." : "Atualizar"}
          </button>
        </div>
      </div>

      {error ? <div className="error-box" role="alert">{error}</div> : null}
      {usage?.enforcement_mode === "meter_only" ? (
        <div className="info-box" role="status">
          Piloto de medição ativo: todo uso está sendo registrado, mas nenhuma função será bloqueada ao terminar a franquia.
        </div>
      ) : null}
      {usage?.enforcement_mode === "enforce" && exhausted.length ? (
        <div className="error-box" role="alert">
          Sem franquia disponível para {exhausted.map((item) => item.label).join(", ")}. O chat humano e os demais recursos continuam funcionando normalmente.
        </div>
      ) : null}

      {usage ? (
        <div className="settings-grid">
          <div className="settings-summary">
            <span>Plano atual</span>
            <strong>{usage.plan.name}</strong>
          </div>
          <div className="settings-summary">
            <span>Ciclo atual</span>
            <strong>{formatCycle(usage.cycle_started_at, usage.cycle_ends_at)}</strong>
          </div>
          <div className="settings-summary">
            <span>Atendimentos ativos agora</span>
            <strong>{formatNumber(usage.active_ai_attendances)}</strong>
          </div>
        </div>
      ) : null}

      <DataTable
        data={visibleResources}
        empty="Nenhuma franquia comercial disponível."
        columns={[
          { key: "resource", label: "Recurso", render: (item) => resourceName(item) },
          { key: "included", label: "Franquia", render: (item) => formatNumber(item.granted) },
          { key: "used", label: "Usado no ciclo", render: (item) => formatNumber(item.measured) },
          { key: "reserved", label: "Em processamento", render: (item) => formatNumber(item.reserved) },
          { key: "available", label: "Disponível", render: (item) => formatNumber(item.available) },
          {
            key: "overage",
            label: "Fora da franquia",
            render: (item) => item.overage ? formatNumber(item.overage) : "—",
          },
        ]}
      />

      <div className="settings-subsection">
        <h3>Uso comercial recente</h3>
        <DataTable
          data={usage?.recent_events ?? []}
          empty="Nenhum consumo comercial registrado neste ciclo."
          columns={[
            {
              key: "date",
              label: "Data",
              render: (item) => new Date(item.created_at).toLocaleString("pt-BR"),
            },
            {
              key: "resource",
              label: "Recurso",
              render: (item) => resourceLabels[item.resource] ?? item.resource,
            },
            { key: "units", label: "Unidades", render: (item) => formatNumber(item.units) },
            {
              key: "allowance",
              label: "Situação",
              render: (item) => item.within_allowance ? "Dentro da franquia" : "Medição excedente",
            },
          ]}
        />
      </div>
    </Card>
  );
}

const resourceLabels: Record<string, string> = {
  ai_attendance: "Atendimento da IA (janela de 24h)",
  image_optimization: "Otimização de foto com IA",
  property_search_ai: "Descoberta web com IA",
  property_search_standard: "Busca de imóveis",
};

function resourceName(item: CommercialResourceUsage) {
  return resourceLabels[item.resource] ?? item.label;
}

function modeLabel(mode: CommercialUsage["enforcement_mode"]) {
  return mode === "meter_only" ? "piloto sem bloqueio" : "franquias ativas";
}

function formatCycle(start: string, end: string) {
  const formatter = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });
  return `${formatter.format(new Date(start))} a ${formatter.format(new Date(end))}`;
}
