import { ApiError, request } from "../api/client";
import type { CommercialUsage, EvolutionWhatsappConnection, NetworkSettings } from "../api/types";

import { jobsUnavailableAlert } from "./operationalAlerts";

/** A problem worth the user's attention, with the place in the app where it gets fixed. */
export type OperationalAlert = {
  key: string;
  message: string;
  action?: { label: string; href: string };
};

const settingsLink = (tab: string, label: string) => ({ label, href: `/configuracoes?aba=${tab}` });

/** Operational checks shown on the dashboard and in the user menu's notifications. */
export async function loadOperationalAlerts(token: string | null): Promise<OperationalAlert[]> {
  const [creditResult, whatsappResult, jobsResult, networkResult] = await Promise.allSettled([
    request<CommercialUsage>("/usage/commercial", {}, token),
    request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/status", {}, token),
    request<Array<{ status: string }>>("/message-jobs?limit=50", {}, token),
    request<NetworkSettings>("/network/settings", {}, token),
  ]);
  const alerts: OperationalAlert[] = [];
  const plan = settingsLink("billing", "Ver plano");
  if (creditResult.status === "rejected") {
    alerts.push({ key: "plan-unknown", message: "Não foi possível verificar as franquias do plano." });
  }
  if (creditResult.status === "fulfilled" && creditResult.value.enforcement_mode === "enforce") {
    const exhausted = new Set(
      creditResult.value.resources.filter((item) => item.available <= 0).map((item) => item.resource),
    );
    if (exhausted.has("ai_attendance")) {
      alerts.push({ key: "ai-quota", message: "Franquia da IA encerrada: novas conversas vão para atendimento humano.", action: plan });
    }
    if (exhausted.has("property_search_standard")) {
      alerts.push({ key: "search-quota", message: "Franquia de buscas de imóveis encerrada.", action: plan });
    }
    if (exhausted.has("image_optimization")) {
      alerts.push({ key: "image-quota", message: "Franquia de otimização de fotos encerrada.", action: plan });
    }
  }
  if (whatsappResult.status === "fulfilled" && whatsappResult.value.status !== "connected") {
    alerts.push({ key: "whatsapp", message: "WhatsApp não está conectado.", action: settingsLink("channels", "Conectar") });
  }
  if (whatsappResult.status === "rejected") {
    alerts.push({ key: "whatsapp-unknown", message: "Não foi possível consultar o WhatsApp.", action: settingsLink("channels", "Ver canais") });
  }
  if (jobsResult.status === "fulfilled") {
    const failed = jobsResult.value.filter((job) => ["failed", "delivery_unknown"].includes(job.status)).length;
    if (failed) {
      alerts.push({
        key: "jobs",
        message: `${failed} ${failed === 1 ? "mensagem não foi entregue" : "mensagens não foram entregues"} e ${failed === 1 ? "precisa" : "precisam"} de revisão.`,
        action: { label: "Ver conversas", href: "/conversas" },
      });
    }
  } else {
    alerts.push({
      key: "jobs-unknown",
      message: jobsUnavailableAlert(jobsResult.reason instanceof ApiError ? jobsResult.reason.status : undefined),
    });
  }
  if (networkResult.status === "fulfilled" && networkResult.value.pending_received > 0) {
    const count = networkResult.value.pending_received;
    alerts.push({
      key: "network",
      message: `${count} pedido${count === 1 ? "" : "s"} de parceria aguardando resposta na Rede ImmobIA.`,
      action: settingsLink("network", "Responder"),
    });
  }
  return alerts;
}
