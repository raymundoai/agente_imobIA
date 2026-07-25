import { useEffect, useState } from "react";
import {
  Building2,
  CheckCircle2,
  MessageSquare,
  UserCheck,
  Users,
} from "lucide-react";
import { request } from "../api/client";
import type { DashboardStats } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { Card } from "../components/Card";
import { MetricCard } from "../components/MetricCard";

export function DashboardPage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    void request<DashboardStats>("/dashboard/stats", {}, token).then(setStats);
  }, [token]);

  return (
    <section className="page-stack">
      <div className="metric-grid">
        <MetricCard
          detail="Conversas registradas na empresa"
          icon={MessageSquare}
          label="Conversas WhatsApp"
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

      <Card className="health-card">
        <CheckCircle2 size={18} />
        <span>Métricas exibidas somente para a empresa acessada.</span>
        <Badge variant="success">Operação saudável</Badge>
      </Card>
    </section>
  );
}
