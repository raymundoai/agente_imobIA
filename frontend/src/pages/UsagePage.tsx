import { useEffect, useState } from "react";
import { request } from "../api/client";
import type { UsageSummaryItem } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/DataTable";
import { formatCurrency } from "../lib/format";

export function UsagePage() {
  const { token } = useAuth();
  const [items, setItems] = useState<UsageSummaryItem[]>([]);

  useEffect(() => {
    void request<UsageSummaryItem[]>("/usage/summary", {}, token).then(setItems);
  }, [token]);

  return (
    <section className="page-stack">
      <header className="page-header">
        <span className="eyebrow">Métricas</span>
        <h1>Uso</h1>
        <p>Resumo de volume e custo estimado por módulo.</p>
      </header>
      <DataTable
        data={items}
        empty="Sem uso registrado."
        columns={[
          { key: "module", label: "Módulo", render: (item) => item.module },
          { key: "type", label: "Tipo", render: (item) => item.type },
          { key: "quantity", label: "Quantidade", render: (item) => item.quantity },
          {
            key: "cost",
            label: "Custo estimado",
            render: (item) => formatCurrency(item.estimated_cost),
          },
        ]}
      />
    </section>
  );
}
