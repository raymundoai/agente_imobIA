import { FormEvent, useEffect, useRef, useState } from "react";
import { CheckCircle2, Copy, CreditCard, ExternalLink, Image, Loader2, MessageSquare, QrCode, RefreshCw, Search } from "lucide-react";
import { request } from "../../api/client";
import type { BillingOverview, BillingPlan, PackOffer, PackOrder, PixCharge } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Card } from "../../components/Card";
import { Modal } from "../../components/Modal";
import { BILLING_CHANGED_EVENT } from "../../components/TrialBanner";
import { formatDocument, formatNumber } from "../../lib/format";

const POLL_INTERVAL_MS = 5000;
const awaitingPayment = new Set(["creating", "pending_payment", "past_due"]);

const subscriptionStatusLabels: Record<string, string> = {
  creating: "Confirmando com o Asaas",
  pending_payment: "Aguardando pagamento",
  active: "Ativa",
  past_due: "Pagamento em atraso",
};

const PACK_LABELS: Record<PackOffer["resource"], { title: string; unit: string; icon: typeof Search }> = {
  ai_attendance: { title: "Atendimentos de IA", unit: "atendimentos", icon: MessageSquare },
  property_search_standard: { title: "Buscas de imóveis", unit: "buscas", icon: Search },
  image_optimization: { title: "Otimização de fotos", unit: "fotos", icon: Image },
};

export function BillingSettingsPanel() {
  const { token } = useAuth();
  const role = getTokenClaims(token)?.role;
  const isAdmin = role === "admin";
  const canBuyPacks = role === "admin" || role === "gestor";
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [planCode, setPlanCode] = useState("");
  const [billingType, setBillingType] = useState<"PIX" | "CREDIT_CARD">("CREDIT_CARD");
  const [contact, setContact] = useState({ name: "", email: "", cpf_cnpj: "" });
  // Kept across retries so an uncertain response never creates a second subscription.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const [submitting, setSubmitting] = useState(false);
  const [justActivated, setJustActivated] = useState(false);
  const previousStatus = useRef<string | null>(null);

  function applyOverview(next: BillingOverview) {
    const status = next.subscription?.status ?? null;
    if (previousStatus.current && awaitingPayment.has(previousStatus.current) && status === "active") {
      setJustActivated(true);
      window.dispatchEvent(new Event(BILLING_CHANGED_EVENT));
    }
    previousStatus.current = status;
    setOverview(next);
  }

  async function load() {
    setLoading(true);
    try {
      const next = await request<BillingOverview>("/billing", {}, token);
      applyOverview(next);
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

  // Arriving from "Comprar pacote" (#pacotes), bring the packs into view once they render.
  const hasPacks = Boolean(overview?.packs.length);
  useEffect(() => {
    if (hasPacks && window.location.hash === "#pacotes") {
      document.getElementById("pacotes")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [hasPacks]);

  // While a charge is open, keep checking so the screen flips to "active" on its own
  // as soon as the payment webhook is processed.
  const [packOrder, setPackOrder] = useState<PackOrder | null>(null);
  const waitingPack = Boolean(overview?.pack_orders.some((order) => order.status === "pending_payment"));
  const waiting = Boolean(overview?.subscription && awaitingPayment.has(overview.subscription.status)) || waitingPack;
  useEffect(() => {
    if (!waiting) return;
    const handle = window.setInterval(() => {
      request<BillingOverview>("/billing", {}, token).then(applyOverview).catch(() => undefined);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting, token]);

  async function subscribe(event: FormEvent) {
    event.preventDefault();
    const digits = contact.cpf_cnpj.replace(/\D/g, "");
    if (digits.length !== 11 && digits.length !== 14) {
      setError("Informe o CPF ou CNPJ de quem vai pagar.");
      return;
    }
    // Opened during the click so the browser does not block it as a popup;
    // it receives the Asaas card page once the subscription exists.
    const cardWindow = billingType === "CREDIT_CARD" ? window.open("", "_blank") : null;
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
      applyOverview(next);
      setIdempotencyKey(crypto.randomUUID());
      const invoiceUrl = next.subscription?.invoice_url;
      if (cardWindow && invoiceUrl) cardWindow.location.href = invoiceUrl;
      else cardWindow?.close();
    } catch (reason) {
      cardWindow?.close();
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

      {justActivated && subscription?.status === "active" ? (
        <div className="billing-confirmed" role="status">
          <CheckCircle2 size={20} />
          <div>
            <strong>Pagamento confirmado!</strong>
            <span>O plano {subscription.plan_name} já está ativo. Obrigado!</span>
          </div>
        </div>
      ) : null}

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
          {subscription.billing_type === "CREDIT_CARD" && subscription.invoice_url && waiting ? (
            <a className="primary-button" href={subscription.invoice_url} rel="noreferrer" target="_blank">
              Pagar com cartão
              <ExternalLink size={14} />
            </a>
          ) : null}
        </div>
      ) : null}

      {subscription && waiting && subscription.billing_type === "PIX" ? <PixPayment invoiceUrl={subscription.invoice_url} token={token} /> : null}
      {subscription && waiting && subscription.billing_type === "CREDIT_CARD" ? (
        <p className="billing-waiting" aria-live="polite">
          <Loader2 className="spin" size={16} />
          Aguardando a confirmação do pagamento. Esta tela atualiza sozinha quando o cartão for aprovado na página do Asaas.
        </p>
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

      {overview.packs.length ? (
        <PackSection
          canBuy={canBuyPacks}
          onBought={(order) => {
            setPackOrder(order);
            void load();
          }}
          onOpenOrder={setPackOrder}
          orders={overview.pack_orders}
          packs={overview.packs}
          token={token}
        />
      ) : null}

      {packOrder ? (
        <PackPaymentModal
          onClose={() => setPackOrder(null)}
          order={overview.pack_orders.find((order) => order.id === packOrder.id) ?? packOrder}
          token={token}
        />
      ) : null}
    </Card>
  );
}

function PackSection({
  packs,
  orders,
  canBuy,
  token,
  onBought,
  onOpenOrder,
}: {
  packs: PackOffer[];
  orders: PackOrder[];
  canBuy: boolean;
  token: string | null;
  onBought: (order: PackOrder) => void;
  onOpenOrder: (order: PackOrder) => void;
}) {
  const [buying, setBuying] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // One key per resource, kept across retries so a lost response never charges twice.
  const keys = useRef<Record<string, string>>({});

  async function buy(pack: PackOffer) {
    keys.current[pack.resource] ??= crypto.randomUUID();
    setBuying(pack.resource);
    setError(null);
    try {
      const order = await request<PackOrder>(
        "/billing/packs",
        { method: "POST", body: JSON.stringify({ resource: pack.resource, idempotency_key: keys.current[pack.resource] }) },
        token,
      );
      delete keys.current[pack.resource];
      onBought(order);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível gerar a cobrança do pacote.");
    } finally {
      setBuying(null);
    }
  }

  const pending = orders.filter((order) => order.status === "pending_payment");
  return (
    <section className="pack-section" id="pacotes">
      <div>
        <h3>Pacotes adicionais</h3>
        <p>Se a franquia do mês acabar, compre um pacote avulso. Os créditos entram assim que o pagamento é confirmado e valem por 90 dias.</p>
      </div>
      <div className="pack-grid">
        {packs.map((pack) => {
          const label = PACK_LABELS[pack.resource];
          const Icon = label.icon;
          return (
            <article className="pack-card" key={pack.resource}>
              <span className="pack-icon"><Icon size={18} /></span>
              <strong>{formatNumber(pack.units)} {label.unit}</strong>
              <small>{label.title}</small>
              <span className="pack-price">{formatBrl(pack.price_cents)}</span>
              {canBuy ? (
                <button className="secondary-button" disabled={buying !== null} onClick={() => void buy(pack)} type="button">
                  {buying === pack.resource ? <><Loader2 className="spin" size={14} /> Gerando…</> : "Comprar"}
                </button>
              ) : null}
            </article>
          );
        })}
      </div>
      {!canBuy ? <small className="field-hint">Somente administradores e gestores podem comprar pacotes.</small> : null}
      {error ? <div className="error-box" role="alert">{error}</div> : null}
      {pending.length ? (
        <ul className="pack-pending">
          {pending.map((order) => (
            <li key={order.id}>
              <span>{formatNumber(order.units)} {PACK_LABELS[order.resource].unit} · {formatBrl(order.value_cents)} · aguardando pagamento</span>
              <button className="link-button" onClick={() => onOpenOrder(order)} type="button">Pagar</button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function PackPaymentModal({ order, token, onClose }: { order: PackOrder; token: string | null; onClose: () => void }) {
  const paid = order.status === "paid";
  return (
    <Modal
      description={paid ? undefined : `${formatNumber(order.units)} ${PACK_LABELS[order.resource].unit} por ${formatBrl(order.value_cents)}`}
      footer={<button className={paid ? "primary-button" : "secondary-button"} onClick={onClose} type="button">{paid ? "Concluir" : "Fechar"}</button>}
      onClose={onClose}
      size="wide"
      title={paid ? "Pacote liberado" : "Pagar pacote adicional"}
    >
      {paid ? (
        <div className="qr-state qr-success">
          <CheckCircle2 size={40} />
          <strong>{formatNumber(order.units)} {PACK_LABELS[order.resource].unit} adicionados</strong>
          <span>Os créditos já estão disponíveis e valem por 90 dias.</span>
        </div>
      ) : (
        <PixPayment endpoint={`/billing/packs/${order.id}/pix`} invoiceUrl={order.invoice_url} token={token} />
      )}
    </Modal>
  );
}

function PixPayment({
  token,
  invoiceUrl,
  endpoint = "/billing/pix",
}: {
  token: string | null;
  invoiceUrl?: string | null;
  endpoint?: string;
}) {
  const [pix, setPix] = useState<PixCharge | null>(null);
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setFailed(false);
    request<PixCharge>(endpoint, {}, token)
      .then((value) => {
        setPix(value);
        setError(null);
      })
      // The payment provider's own message is technical; the way out is what matters here.
      .catch(() => setFailed(true));
  }, [token, attempt, endpoint]);

  async function copy() {
    if (!pix) return;
    try {
      await navigator.clipboard.writeText(pix.payload);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setError("Não foi possível copiar. Selecione o código e copie manualmente.");
    }
  }

  if (failed) {
    return (
      <div className="pix-unavailable" role="alert">
        <div>
          <strong>Não conseguimos gerar o QR Code do PIX agora.</strong>
          <span>O sistema de pagamentos não respondeu. A cobrança já está criada; tente de novo ou pague direto pela página segura dela.</span>
        </div>
        <div className="pix-unavailable-actions">
          <button className="secondary-button" onClick={() => setAttempt((value) => value + 1)} type="button">Tentar de novo</button>
          {invoiceUrl ? (
            <a className="primary-button" href={invoiceUrl} rel="noreferrer" target="_blank">
              Pagar pela página da cobrança
              <ExternalLink size={14} />
            </a>
          ) : null}
        </div>
      </div>
    );
  }
  if (!pix) return <div className="empty-state" aria-live="polite"><Loader2 className="spin" size={16} /> Gerando QR Code do PIX...</div>;

  return (
    <div className="pix-payment">
      <img alt="QR Code do PIX para pagamento" className="pix-qr" src={`data:image/png;base64,${pix.encoded_image}`} />
      <div className="pix-details">
        <strong>Pague {formatBrl(pix.value_cents)} com PIX</strong>
        <span>Abra o app do seu banco, escolha pagar com PIX e leia o QR Code, ou use o código abaixo.</span>
        <label className="pix-code">
          <span>PIX copia e cola</span>
          <textarea readOnly rows={3} value={pix.payload} onFocus={(event) => event.target.select()} />
        </label>
        <button className="secondary-button" onClick={() => void copy()} type="button">
          {copied ? <CheckCircle2 size={15} /> : <Copy size={15} />}
          {copied ? "Código copiado" : "Copiar código"}
        </button>
        {error ? <small className="field-hint error">{error}</small> : null}
        {pix.expiration_date ? (
          <small>Válido até {new Date(pix.expiration_date.replace(" ", "T")).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}.</small>
        ) : null}
        <p className="billing-waiting" aria-live="polite">
          <Loader2 className="spin" size={16} />
          Aguardando o pagamento. Esta tela atualiza sozinha.
        </p>
      </div>
    </div>
  );
}

function PlanOption({ plan, selected, onSelect }: { plan: BillingPlan; selected: boolean; onSelect: () => void }) {
  return (
    <label className={selected ? "plan-option selected" : "plan-option"}>
      <input checked={selected} name="plan" type="radio" onChange={onSelect} />
      <strong>{plan.name}</strong>
      {plan.list_price_cents > plan.monthly_price_cents ? (
        <span className="plan-beta">
          <s>{formatBrl(plan.list_price_cents)}</s>
          <em>Condição beta</em>
        </span>
      ) : null}
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
  if (overview.status === "pending") return "Escolha um plano para ativar a IA";
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
  if (overview.status === "pending") {
    return overview.beta_pricing
      ? "Sua conta tem a condição especial de beta tester. O atendimento com IA, as buscas e a otimização de fotos começam assim que a primeira mensalidade for paga."
      : "O atendimento com IA, as buscas e a otimização de fotos começam assim que a primeira mensalidade for paga.";
  }
  if (overview.status === "past_due") return "Você ainda usa o que resta deste mês, mas o plano não renova até o pagamento.";
  if (overview.status === "cancelled") return "IA e buscas estão bloqueadas. Escolha um plano para voltar a usar.";
  return `Ciclo atual até ${new Date(overview.cycle_ends_at).toLocaleDateString("pt-BR")}.`;
}

function formatBrl(cents: number) {
  return new Intl.NumberFormat("pt-BR", { currency: "BRL", style: "currency" }).format(cents / 100);
}
