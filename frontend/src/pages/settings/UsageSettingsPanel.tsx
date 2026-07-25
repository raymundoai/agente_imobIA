import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { UsageSummaryItem } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable";
import { formatCurrency } from "../../lib/format";

export function UsageSettingsPanel() {
  const { token } = useAuth();
  const [items, setItems] = useState<UsageSummaryItem[]>([]);

  useEffect(() => {
    void request<UsageSummaryItem[]>("/usage/summary", {}, token)
      .then(setItems)
      .catch(() => setItems([]));
  }, [token]);

  const total = items.reduce((sum, item) => sum + Number(item.estimated_cost || 0), 0);
  const quantity = items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Uso e custos</h2>
          <p>Acompanhe volume de atendimento, automações e custo estimado da IA.</p>
        </div>
        <span className="settings-status">{formatCurrency(String(total))}</span>
      </div>

      <div className="settings-grid">
        <div className="settings-summary">
          <span>Registros</span>
          <strong>{quantity}</strong>
        </div>
        <div className="settings-summary">
          <span>Custo estimado</span>
          <strong>{formatCurrency(String(total))}</strong>
        </div>
      </div>

      <DataTable
        data={items}
        empty="Sem uso registrado ainda."
        columns={[
          { key: "module", label: "Área", render: (item) => moduleLabels[item.module] ?? item.module },
          { key: "type", label: "Evento", render: (item) => typeLabels[item.type] ?? item.type },
          { key: "quantity", label: "Quantidade", render: (item) => item.quantity },
          {
            key: "cost",
            label: "Custo estimado",
            render: (item) => formatCurrency(item.estimated_cost),
          },
        ]}
      />
    </Card>
  );
}

const moduleLabels: Record<string, string> = {
  ai: "IA",
  conversations: "Conversas",
  capture: "Buscador",
  maintenance: "Pós-contrato",
};

const typeLabels: Record<string, string> = {
  conversation: "Conversa",
  message: "Mensagem",
  ai_call: "Chamada de IA",
  capture: "Captação",
  handoff: "Passagem para equipe",
  ticket: "Chamado",
};
