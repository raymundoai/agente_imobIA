import { ApiError, request } from "../api/client";
import type {
  CommercialUsage,
  EvolutionWhatsappConnection,
  NetworkSettings,
  TelegramConnection,
} from "../api/types";

import { jobsUnavailableAlert } from "./operationalAlerts";

/** Operational checks shown on the dashboard and in the user menu's notifications. */
export async function loadOperationalAlerts(token: string | null): Promise<string[]> {
  const [creditResult, whatsappResult, telegramResult, jobsResult, networkResult] = await Promise.allSettled([
    request<CommercialUsage>("/usage/commercial", {}, token),
    request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/status", {}, token),
    request<TelegramConnection>("/integrations/telegram/status", {}, token),
    request<Array<{ status: string }>>("/message-jobs?limit=50", {}, token),
    request<NetworkSettings>("/network/settings", {}, token),
  ]);
  const alerts: string[] = [];
  if (creditResult.status === "rejected") alerts.push("Não foi possível verificar as franquias do plano.");
  if (creditResult.status === "fulfilled" && creditResult.value.enforcement_mode === "enforce") {
    const exhausted = creditResult.value.resources.filter((item) => item.available <= 0);
    if (exhausted.some((item) => item.resource === "ai_attendance")) {
      alerts.push("Franquia da IA encerrada: novas conversas serão encaminhadas para atendimento humano.");
    }
    if (exhausted.some((item) => item.resource === "property_search_standard")) {
      alerts.push("Franquia de buscas de imóveis encerrada.");
    }
    if (exhausted.some((item) => item.resource === "image_optimization")) {
      alerts.push("Franquia de otimização de fotos encerrada.");
    }
  }
  if (whatsappResult.status === "fulfilled" && whatsappResult.value.status !== "connected") {
    alerts.push("WhatsApp não está conectado.");
  }
  if (whatsappResult.status === "rejected") alerts.push("Status do WhatsApp indisponível.");
  if (telegramResult.status === "fulfilled" && telegramResult.value.status !== "connected") {
    alerts.push("Telegram não está conectado.");
  }
  if (telegramResult.status === "rejected") alerts.push("Status do Telegram indisponível.");
  if (jobsResult.status === "fulfilled") {
    const failed = jobsResult.value.filter((job) => ["failed", "delivery_unknown"].includes(job.status)).length;
    if (failed) alerts.push(`${failed} atendimento(s) exigem revisão operacional.`);
  } else {
    alerts.push(jobsUnavailableAlert(jobsResult.reason instanceof ApiError ? jobsResult.reason.status : undefined));
  }
  if (networkResult.status === "fulfilled" && networkResult.value.pending_received > 0) {
    const count = networkResult.value.pending_received;
    alerts.push(`${count} pedido${count === 1 ? "" : "s"} de parceria aguardando resposta na Rede ImmobIA.`);
  }
  return alerts;
}
