import { useEffect, useState } from "react";
import {
  Building2,
  CheckCircle2,
  MessageSquare,
  UserCheck,
  Users,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { request } from "../api/client";
import type { DashboardStats } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { Card } from "../components/Card";
import { MetricCard } from "../components/MetricCard";

const chartData = [
  { day: "01", ai: 8, human: 3 },
  { day: "05", ai: 14, human: 5 },
  { day: "10", ai: 12, human: 4 },
  { day: "15", ai: 19, human: 6 },
  { day: "20", ai: 23, human: 7 },
  { day: "25", ai: 26, human: 8 },
  { day: "30", ai: 31, human: 9 },
];

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
          detail="Captados pelo buscador"
          icon={Building2}
          label="Imóveis"
          value={stats?.properties ?? "—"}
          variation="+ captação"
        />
      </div>

      <div className="dashboard-grid">
        <Card className="chart-card">
          <div className="card-header">
            <div>
              <h2>Atendimentos nos últimos 30 dias</h2>
              <p>Projeção visual para comparar IA versus humano.</p>
            </div>
            <div className="chart-legend">
              <span><i className="legend-primary" /> IA</span>
              <span><i className="legend-muted" /> Humano</span>
            </div>
          </div>
          <div className="chart-wrap">
            <ResponsiveContainer height="100%" width="100%">
              <LineChart data={chartData} margin={{ bottom: 0, left: -20, right: 8, top: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis axisLine={false} dataKey="day" tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip />
                <Line dataKey="ai" dot={false} name="IA" stroke="var(--primary)" strokeWidth={3} />
                <Line
                  dataKey="human"
                  dot={false}
                  name="Humano"
                  stroke="var(--muted-foreground)"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

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
            <span>Imóveis captados: {stats?.properties ?? "—"}</span>
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
