import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { request } from "../api/client";
import type { BillingOverview } from "../api/types";
import { useAuth } from "../auth/AuthContext";

export function openBillingSettings() {
  window.history.pushState({}, "", "/configuracoes?aba=billing");
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function TrialBanner() {
  const { token } = useAuth();
  const [overview, setOverview] = useState<BillingOverview | null>(null);

  useEffect(() => {
    request<BillingOverview>("/billing", {}, token).then(setOverview).catch(() => setOverview(null));
  }, [token]);

  if (!overview || overview.subscription?.status === "active") return null;
  let message: string | null = null;
  if (overview.status === "trial" && overview.trial_ends_at) {
    const days = Math.max(0, Math.ceil((new Date(overview.trial_ends_at).getTime() - Date.now()) / 86_400_000));
    message = days
      ? `Teste grátis: ${days} dia${days === 1 ? "" : "s"} restante${days === 1 ? "" : "s"}.`
      : "Seu teste grátis terminou. Assine para continuar usando a IA e as buscas.";
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
