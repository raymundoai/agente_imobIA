import { FormEvent, useEffect, useState } from "react";
import { CreditCard, ExternalLink, QrCode, RefreshCw } from "lucide-react";
import { request } from "../../api/client";
import type { BillingOverview, BillingPlan } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Card } from "../../components/Card";
import { formatDocument, formatNumber } from "../../lib/format";

const subscriptionStatusLabels: Record<string, string> = {
  creating: "Confirmando com o Asaas",
  pending_payment: "Aguardando pagamento",
  active: "Ativa",
  past_due: "Pagamento em atraso",
};

export function BillingSettingsPanel() {
  const { token } = useAuth();
  const isAdmin = getTokenClaims(token)?.role === "admin";
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [planCode, setPlanCode] = useState("");
  const [billingType, setBillingType] = useState<"PIX" | "CREDIT_CARD">("CREDIT_CARD");
  const [contact, setContact] = useState({ name: "", email: "", cpf_cnpj: "" });
  // Kept across retries so an uncertain response never creates a second subscription.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const next = await request<BillingOverview>("/billing", {}, token);
      setOverview(next);
      setPlanCode((current) => current || next.plans[1]?.code || next.plans[0]?.code || "");
      setContact((current) => ({
        name: current.name || next.contact.name,
        email: current.email || next.contact.email || "",
        cpf_cnpj: current.cpf_cnpj || (next.contact.cpf_cnpj ? formatDocument(next.contact.cpf_cnpj, next.contact.cpf_cnpj.length > 11 ? "cnpj" : "cpf") : ""),
      }));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível carregar o plano.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function subscribe(event: FormEvent) {
    event.preventDefault();
    const digits = contact.cpf_cnpj.replace(/\D/g, "");
    if (digits.length !== 11 && digits.length !== 14) {
      setError("Informe o CPF ou CNPJ de quem vai pagar.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const next = await request<BillingOverview>(
        "/billing/subscription",
        {
          method: "POST",
          body: JSON.stringify({
            plan_code: planCode,
            billing_type: billingType,
            idempotency_key: idempotencyKey,
            customer: { name: contact.name, email: contact.email, cpf_cnpj: digits },
          }),
        },
        token,
      );
      setOverview(next);
      setIdempotencyKey(crypto.randomUUID());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível criar a assinatura.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading && !overview) {
    return <Card className="settings-panel-card"><div className="empty-state" aria-live="polite">Carregando plano...</div></Card>;
  }
  if (!overview) {
    return <Card className="settings-panel-card"><div className="error-box">{error}</div></Card>;
  }

  const subscription = overview.subscription;
  const selectedPlan = overview.plans.find((plan) => plan.code === planCode);

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Plano e cobrança</h2>
          <p>Assinatura mensal processada pelo Asaas. O plano é liberado assim que o pagamento é confirmado.</p>
        </div>
        <button className="button-outline" disabled={loading} onClick={() => void load()} type="button">
          <RefreshCw size={14} />
          Atualizar
        </button>
      </div>

      <div className={`billing-status billing-status-${overview.status}`}>
        <strong>{statusHeadline(overview)}</strong>
        <span>{statusDetail(overview)}</span>
      </div>

      {subscription ? (
        <div className="billing-subscription">
          <div>
            <span className="eyebrow">Assinatura</span>
            <strong>{subscription.plan_name} · {formatBrl(subscription.value_cents)}/mês</strong>
            <span>
              {subscription.billing_type === "CREDIT_CARD" ? "Cartão de crédito" : "PIX"} ·{" "}
              {subscriptionStatusLabels[subscription.status] ?? subscription.status}
            </span>
          </div>
          {subscription.invoice_url && subscription.status !== "active" ? (
            <a className="primary-button" href={subscription.invoice_url} rel="noreferrer" target="_blank">
              Pagar agora
              <ExternalLink size={14} />
            </a>
          ) : null}
        </div>
      ) : null}

      {!subscription && !overview.payments_enabled ? (
        <div className="info-box">A contratação online ainda não está disponível. Fale com o suporte para assinar.</div>
      ) : null}
      {!subscription && overview.payments_enabled && !isAdmin ? (
        <div className="info-box">Somente o administrador da conta pode contratar um plano.</div>
      ) : null}

      {!subscription && overview.payments_enabled && isAdmin ? (
        <form className="billing-form" onSubmit={subscribe}>
          <fieldset className="plan-options">
            <legend>Escolha o plano</legend>
            {overview.plans.map((plan) => (
              <PlanOption key={plan.code} plan={plan} selected={plan.code === planCode} onSelect={() => setPlanCode(plan.code)} />
            ))}
          </fieldset>

          <fieldset className="payment-options">
            <legend>Forma de pagamento</legend>
            <label className={billingType === "CREDIT_CARD" ? "payment-option selected" : "payment-option"}>
              <input checked={billingType === "CREDIT_CARD"} name="billing-type" type="radio" onChange={() => setBillingType("CREDIT_CARD")} />
              <CreditCard size={18} />
              <span>
                <strong>Cartão de crédito</strong>
                <small>Cobrança automática todo mês.</small>
              </span>
            </label>
            <label className={billingType === "PIX" ? "payment-option selected" : "payment-option"}>
              <input checked={billingType === "PIX"} name="billing-type" type="radio" onChange={() => setBillingType("PIX")} />
              <QrCode size={18} />
              <span>
                <strong>PIX</strong>
                <small>Uma cobrança por mês, enviada por email.</small>
              </span>
            </label>
          </fieldset>

          <div className="form-grid">
            <label>
              Nome ou razão social
              <input value={contact.name} onChange={(event) => setContact({ ...contact, name: event.target.value })} />
            </label>
            <label>
              Email financeiro
              <input type="email" value={contact.email} onChange={(event) => setContact({ ...contact, email: event.target.value })} />
            </label>
            <label>
              CPF ou CNPJ
              <input
                inputMode="numeric"
                value={contact.cpf_cnpj}
                onChange={(event) => {
                  const digits = event.target.value.replace(/\D/g, "");
                  setContact({ ...contact, cpf_cnpj: formatDocument(digits, digits.length > 11 ? "cnpj" : "cpf") });
                }}
              />
            </label>
          </div>

          {error ? <div className="error-box">{error}</div> : null}
          <div className="billing-submit">
            <button className="primary-button" disabled={submitting || !selectedPlan} type="submit">
              {submitting ? "Gerando cobrança..." : `Assinar ${selectedPlan?.name ?? ""} por ${selectedPlan ? formatBrl(selectedPlan.monthly_price_cents) : ""}/mês`}
            </button>
            <small>Você será direcionado à página segura do Asaas para pagar. Os dados do cartão não passam pelo ImmobIA.</small>
          </div>
        </form>
      ) : error ? (
        <div className="error-box">{error}</div>
      ) : null}
    </Card>
  );
}

function PlanOption({ plan, selected, onSelect }: { plan: BillingPlan; selected: boolean; onSelect: () => void }) {
  return (
    <label className={selected ? "plan-option selected" : "plan-option"}>
      <input checked={selected} name="plan" type="radio" onChange={onSelect} />
      <strong>{plan.name}</strong>
      <span className="plan-price">{formatBrl(plan.monthly_price_cents)}<small>/mês</small></span>
      <ul>
        <li>{plan.ai_attendances ? `${formatNumber(plan.ai_attendances)} atendimentos de IA` : "Sem atendimento de IA"}</li>
        <li>{formatNumber(plan.property_searches)} buscas de imóveis</li>
        <li>{plan.image_optimizations ? `${formatNumber(plan.image_optimizations)} otimizações de fotos` : "Sem otimização de fotos"}</li>
        <li>Até {formatNumber(plan.max_users)} usuários</li>
      </ul>
    </label>
  );
}

function trialDaysLeft(overview: BillingOverview) {
  if (!overview.trial_ends_at) return null;
  return Math.max(0, Math.ceil((new Date(overview.trial_ends_at).getTime() - Date.now()) / 86_400_000));
}

function statusHeadline(overview: BillingOverview) {
  if (overview.status === "trial") {
    const days = trialDaysLeft(overview);
    return days ? `Teste grátis: ${days} dia${days === 1 ? "" : "s"} restante${days === 1 ? "" : "s"}` : "Seu teste grátis terminou";
  }
  if (overview.status === "active") return `Plano ${overview.plan.name} ativo`;
  if (overview.status === "past_due") return "Pagamento em atraso";
  if (overview.status === "cancelled") return "Assinatura encerrada";
  return `Plano ${overview.plan.name}`;
}

function statusDetail(overview: BillingOverview) {
  if (overview.status === "trial") {
    return overview.trial_ends_at
      ? `O teste vai até ${new Date(overview.trial_ends_at).toLocaleDateString("pt-BR")}. Assine para continuar usando a IA e as buscas.`
      : "";
  }
  if (overview.status === "past_due") return "Você ainda usa o que resta deste mês, mas o plano não renova até o pagamento.";
  if (overview.status === "cancelled") return "IA e buscas estão bloqueadas. Escolha um plano para voltar a usar.";
  return `Ciclo atual até ${new Date(overview.cycle_ends_at).toLocaleDateString("pt-BR")}.`;
}

function formatBrl(cents: number) {
  return new Intl.NumberFormat("pt-BR", { currency: "BRL", style: "currency" }).format(cents / 100);
}
