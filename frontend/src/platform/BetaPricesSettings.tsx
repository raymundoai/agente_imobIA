import { useEffect, useState } from "react";
import { request } from "../api/client";
import { Card } from "../components/Card";

type Plan = {
  code: string;
  name: string;
  monthly_price_cents: number;
  is_public: boolean;
  beta_price_cents: number | null;
};

const brl = (cents: number) => new Intl.NumberFormat("pt-BR", { currency: "BRL", style: "currency" }).format(cents / 100);

/** Beta testers pay these prices instead of the list price (clients are marked in their record). */
export function BetaPricesSettings({ token }: { token: string }) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    request<Plan[]>("/platform/commercial/plans", {}, token)
      .then((items) => {
        const visible = items.filter((plan) => plan.is_public && plan.monthly_price_cents > 0);
        setPlans(visible);
        setDrafts(Object.fromEntries(visible.map((plan) => [plan.code, plan.beta_price_cents ? String(plan.beta_price_cents / 100) : ""])));
      })
      .catch((reason) => setFeedback(reason instanceof Error ? reason.message : "Falha ao carregar os planos."));
  }, [token]);

  async function save(plan: Plan) {
    const raw = (drafts[plan.code] ?? "").replace(",", ".").trim();
    const cents = raw ? Math.round(Number(raw) * 100) : null;
    if (cents !== null && (!Number.isFinite(cents) || cents < 500)) {
      setFeedback("O preço beta precisa ser de pelo menos R$ 5,00 (mínimo do Asaas).");
      return;
    }
    try {
      const updated = await request<Plan>(
        `/platform/commercial/plans/${plan.code}/beta-price`,
        { method: "PATCH", body: JSON.stringify({ beta_price_cents: cents }) },
        token,
      );
      setPlans((current) => current.map((item) => (item.code === updated.code ? updated : item)));
      setFeedback(`Preço beta do ${updated.name} salvo.`);
    } catch (reason) {
      setFeedback(reason instanceof Error ? reason.message : "Não foi possível salvar.");
    }
  }

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Preços beta</h2>
          <p>Clientes marcados como beta tester veem e pagam estes valores. Deixe em branco para cobrar o preço normal.</p>
        </div>
      </div>
      <div className="beta-prices">
        {plans.map((plan) => (
          <div className="beta-price-row" key={plan.code}>
            <strong>{plan.name}</strong>
            <span>Tabela: {brl(plan.monthly_price_cents)}</span>
            <label>
              <span className="sr-only">Preço beta do {plan.name} em reais</span>
              <span className="beta-input">
                R$
                <input
                  inputMode="decimal"
                  onChange={(event) => setDrafts({ ...drafts, [plan.code]: event.target.value })}
                  placeholder="sem preço beta"
                  value={drafts[plan.code] ?? ""}
                />
              </span>
            </label>
            <button className="secondary-button" onClick={() => void save(plan)} type="button">Salvar</button>
          </div>
        ))}
      </div>
      {feedback ? <p className="field-hint" role="status">{feedback}</p> : null}
    </Card>
  );
}
