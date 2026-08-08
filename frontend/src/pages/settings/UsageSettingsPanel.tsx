import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { CreditAccount, CreditLedgerItem, UsageSummaryItem } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable";
import { formatNumber } from "../../lib/format";

export function UsageSettingsPanel() {
  const { token } = useAuth();
  const [items, setItems] = useState<UsageSummaryItem[]>([]);
  const [account, setAccount] = useState<CreditAccount | null>(null);
  const [ledger, setLedger] = useState<CreditLedgerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadUsage() {
    setLoading(true);
    const results = await Promise.allSettled([
      request<UsageSummaryItem[]>("/usage/summary", {}, token),
      request<CreditAccount>("/usage/credits", {}, token),
      request<CreditLedgerItem[]>("/usage/credits/ledger", {}, token),
    ]);
    const failures: string[] = [];
    const [usage, credits, transactions] = results;
    if (usage.status === "fulfilled") setItems(usage.value);
    else failures.push("resumo de uso");
    if (credits.status === "fulfilled") setAccount(credits.value);
    else failures.push("saldo de créditos");
    if (transactions.status === "fulfilled") setLedger(transactions.value);
    else failures.push("extrato");
    setError(failures.length ? `Não foi possível atualizar: ${failures.join(", ")}. Os demais dados continuam disponíveis.` : null);
    setLoading(false);
  }

  useEffect(() => {
    void loadUsage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const total = items.reduce((sum, item) => sum + Number(item.estimated_cost || 0), 0);
  const quantity = items.reduce((sum, item) => sum + item.quantity, 0);

  if (loading) return <Card className="settings-panel-card"><div className="empty-state" aria-live="polite">Carregando uso e créditos...</div></Card>;
  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Uso e custos</h2>
          <p>Acompanhe volume de atendimento, automações e custo estimado da IA.</p>
        </div>
        <div className="settings-header-actions">
          <span className="settings-status">
            {account ? `${formatNumber(account.available_credits)} créditos disponíveis` : "Saldo indisponível"}
          </span>
          <button className="button-outline" disabled={loading} onClick={() => void loadUsage()} type="button">Atualizar</button>
        </div>
      </div>

      {error ? <div className="error-box" role="alert">{error}</div> : null}

      <div className="settings-grid">
        {account && account.enforcement_mode === "enforce" && account.available_credits <= 0 ? (
          <div className="error-box form-span-2" role="alert">Saldo indisponível. Atendimento por IA e tratamento de imagens podem ser bloqueados.</div>
        ) : null}
        <div className="settings-summary">
          <span>Saldo total</span>
          <strong>{formatNumber(account?.balance_credits ?? 0)}</strong>
        </div>
        <div className="settings-summary">
          <span>Créditos reservados</span>
          <strong>{formatNumber(account?.reserved_credits ?? 0)}</strong>
        </div>
        <div className="settings-summary">
          <span>Créditos disponíveis</span>
          <strong>{formatNumber(account?.available_credits ?? 0)}</strong>
        </div>
        <div className="settings-summary">
          <span>Custo OpenAI estimado</span>
          <strong>{formatUsd(total)}</strong>
        </div>
        <div className="settings-summary">
          <span>Eventos medidos</span>
          <strong>{formatNumber(quantity)}</strong>
        </div>
        <div className="settings-summary">
          <span>Política</span>
          <strong>
            {account?.unlimited_messages
              ? "Mensagens ilimitadas"
              : account?.enforcement_mode === "enforce"
                ? "Bloqueio sem saldo"
                : "Somente medição"}
          </strong>
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
            render: (item) => formatUsd(Number(item.estimated_cost)),
          },
        ]}
      />

      <div className="settings-subsection">
        <h3>Extrato de créditos</h3>
        <DataTable
          data={ledger}
          empty="Nenhum lançamento de crédito ainda."
          columns={[
            {
              key: "date",
              label: "Data",
              render: (item) => new Date(item.created_at).toLocaleString("pt-BR"),
            },
            {
              key: "event",
              label: "Evento",
              render: (item) =>
                item.kind === "grant"
                  ? item.description ?? "Crédito concedido"
                  : resourceLabels[item.resource ?? ""] ?? item.resource ?? item.kind,
            },
            { key: "model", label: "Modelo", render: (item) => item.model ?? "—" },
            {
              key: "delta",
              label: "Créditos",
              render: (item) => `${item.delta_credits > 0 ? "+" : ""}${formatNumber(item.delta_credits)}`,
            },
            {
              key: "balance",
              label: "Saldo",
              render: (item) => formatNumber(item.balance_after),
            },
          ]}
        />
      </div>
    </Card>
  );
}

const moduleLabels: Record<string, string> = {
  ai: "IA",
  conversations: "Conversas",
};

const typeLabels: Record<string, string> = {
  conversation: "Conversa",
  message: "Mensagem",
  ai_call: "Chamada de IA",
  handoff: "Passagem para equipe",
};

const resourceLabels: Record<string, string> = {
  ai_message: "Atendimento por IA",
  image_edit: "Tratamento de imagem",
};

function formatUsd(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    currency: "USD",
    minimumFractionDigits: 4,
    style: "currency",
  }).format(value);
}
