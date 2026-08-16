import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  MessageSquare,
  UserCheck,
  Users,
} from "lucide-react";
import { ApiError, request } from "../api/client";
import type { CommercialUsage, DashboardStats, EvolutionWhatsappConnection, TelegramConnection } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { Card } from "../components/Card";
import { MetricCard } from "../components/MetricCard";
import { jobsUnavailableAlert } from "../lib/operationalAlerts";

export function DashboardPage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<string[]>([]);

  useEffect(() => {
    setLoading(true);
    void Promise.allSettled([
      request<DashboardStats>("/dashboard/stats", {}, token),
      request<CommercialUsage>("/usage/commercial", {}, token),
      request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/status", {}, token),
      request<TelegramConnection>("/integrations/telegram/status", {}, token),
      request<Array<{ status: string }>>("/message-jobs?limit=50", {}, token),
    ]).then(([statsResult, creditResult, whatsappResult, telegramResult, jobsResult]) => {
      if (statsResult.status === "rejected") {
        setError(statsResult.reason instanceof Error ? statsResult.reason.message : "Falha ao carregar o painel.");
        setStats(null);
      } else {
        setStats(statsResult.value);
        setError(null);
      }
      const operational: string[] = [];
      if (creditResult.status === "rejected") operational.push("Não foi possível verificar as franquias do plano.");
      if (creditResult.status === "fulfilled" && creditResult.value.enforcement_mode === "enforce") {
        const exhausted = creditResult.value.resources.filter((item) => item.available <= 0);
        if (exhausted.some((item) => item.resource === "ai_attendance")) {
          operational.push("Franquia da IA encerrada: novas conversas serão encaminhadas para atendimento humano.");
        }
        if (exhausted.some((item) => item.resource === "property_search_standard")) {
          operational.push("Franquia de buscas de imóveis encerrada.");
        }
        if (exhausted.some((item) => item.resource === "image_optimization")) {
          operational.push("Franquia de otimização de fotos encerrada.");
        }
      }
      if (whatsappResult.status === "fulfilled" && whatsappResult.value.status !== "connected") {
        operational.push("WhatsApp não está conectado.");
      }
      if (whatsappResult.status === "rejected") operational.push("Status do WhatsApp indisponível.");
      if (telegramResult.status === "fulfilled" && telegramResult.value.status !== "connected") {
        operational.push("Telegram não está conectado.");
      }
      if (telegramResult.status === "rejected") operational.push("Status do Telegram indisponível.");
      if (jobsResult.status === "fulfilled") {
        const failed = jobsResult.value.filter((job) => ["failed", "delivery_unknown"].includes(job.status)).length;
        if (failed) operational.push(`${failed} atendimento(s) exigem revisão operacional.`);
      } else {
        operational.push(
          jobsUnavailableAlert(
            jobsResult.reason instanceof ApiError ? jobsResult.reason.status : undefined,
          ),
        );
      }
      setAlerts(operational);
    }).finally(() => setLoading(false));
  }, [token]);

  if (loading) return <section className="empty-state large" aria-live="polite">Carregando visão geral...</section>;
  if (error) return <section className="error-box" role="alert">{error}</section>;

  return (
    <section className="page-stack">
      <div className="metric-grid">
        <MetricCard
          detail="Conversas registradas na empresa"
          icon={MessageSquare}
          label="Conversas multicanal"
          value={stats?.conversations ?? "—"}
        />
        <MetricCard
          detail="Demandas qualificadas ou criadas"
          icon={Users}
          label="Demandas de leads"
          value={stats?.leads ?? "—"}
        />
        <MetricCard
          detail="Casos em atendimento humano"
          icon={UserCheck}
          label="Handoffs"
          value={stats?.handoffs ?? "—"}
        />
        <MetricCard
          detail="Imóveis disponíveis na carteira"
          icon={Building2}
          label="Imóveis"
          value={stats?.properties ?? "—"}
        />
      </div>

      <div className="dashboard-grid">
        <Card>
          <div className="card-header">
            <div>
              <h2>Atividade recente</h2>
              <p>Resumo operacional do MVP.</p>
            </div>
          </div>
          <div className="activity-list">
            <span>Demandas: {stats?.leads ?? "—"}</span>
            <span>Conversas: {stats?.conversations ?? "—"}</span>
            <span>Imóveis na carteira: {stats?.properties ?? "—"}</span>
          </div>
        </Card>
      </div>

      {alerts.length ? (
        <Card className="health-card operational-warning" role="alert">
          <AlertTriangle size={18} />
          <div>{alerts.map((alert) => <p key={alert}>{alert}</p>)}</div>
          <Badge variant="muted">Atenção</Badge>
        </Card>
      ) : (
        <Card className="health-card">
          <CheckCircle2 size={18} />
          <span>Nenhum alerta foi encontrado nas verificações realizadas.</span>
          <Badge variant="success">Sem alertas detectados</Badge>
        </Card>
      )}
    </section>
  );
}
