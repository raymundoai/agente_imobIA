import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { request } from "../api/client";
import type { BillingOverview } from "../api/types";
import { useAuth } from "../auth/AuthContext";

export const BILLING_CHANGED_EVENT = "immobia:billing-changed";

export function openBillingSettings() {
  window.history.pushState({}, "", "/configuracoes?aba=billing");
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function TrialBanner() {
  const { token } = useAuth();
  const [overview, setOverview] = useState<BillingOverview | null>(null);

  useEffect(() => {
    const load = () =>
      request<BillingOverview>("/billing", {}, token).then(setOverview).catch(() => setOverview(null));
    void load();
    window.addEventListener(BILLING_CHANGED_EVENT, load);
    return () => window.removeEventListener(BILLING_CHANGED_EVENT, load);
  }, [token]);

  if (!overview || overview.subscription?.status === "active") return null;
  let message: string | null = null;
  if (overview.status === "trial" && overview.trial_ends_at) {
    const days = Math.max(0, Math.ceil((new Date(overview.trial_ends_at).getTime() - Date.now()) / 86_400_000));
    message = days
      ? `Teste grátis: ${days} dia${days === 1 ? "" : "s"} restante${days === 1 ? "" : "s"}.`
      : "Seu teste grátis terminou. Assine para continuar usando a IA e as buscas.";
  } else if (overview.status === "pending") {
    message = overview.beta_pricing
      ? "Conta pronta, com condição de beta tester. Escolha um plano para ativar a IA."
      : "Conta pronta. Escolha um plano para ativar a IA, as buscas e a otimização de fotos.";
  } else if (overview.status === "past_due") {
    message = "Há um pagamento em atraso. O plano não renova até a quitação.";
  } else if (overview.status === "cancelled" && overview.plan.monthly_price_cents > 0) {
    message = "Sua assinatura foi encerrada. IA e buscas estão bloqueadas.";
  }
  if (!message) return null;

  return (
    <div className="trial-banner" role="status">
      <Sparkles size={16} />
      <span>{message}</span>
      <button className="link-button" onClick={openBillingSettings} type="button">
        {overview.subscription ? "Ver pagamento" : "Escolher plano"}
      </button>
    </div>
  );
}
