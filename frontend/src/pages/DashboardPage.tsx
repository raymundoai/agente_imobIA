import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Building2,
  Check,
  CheckCircle2,
  MessageSquare,
  SearchCheck,
  Users,
} from "lucide-react";
import { request } from "../api/client";
import type { ContactKind, ConversationTimeline, DashboardStats } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Card } from "../components/Card";
import { formatNumber } from "../lib/format";
import { openAppLink } from "../lib/appNavigation";
import { loadOperationalAlerts, type OperationalAlert } from "../lib/loadOperationalAlerts";

const contactKindOptions: Array<{ value: ContactKind | "all"; label: string }> = [
  { value: "all", label: "Todos" },
  { value: "lead", label: "Leads" },
  { value: "owner", label: "Proprietários" },
  { value: "tenant", label: "Inquilinos" },
  { value: "client", label: "Clientes" },
];
const periods = [7, 30, 90] as const;
type Period = (typeof periods)[number];

export function DashboardPage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<OperationalAlert[]>([]);
  const [contactKind, setContactKind] = useState<ContactKind | "all">("all");
  const [period, setPeriod] = useState<Period>(30);
  const [timeline, setTimeline] = useState<ConversationTimeline | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(true);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    void Promise.allSettled([
      request<DashboardStats>("/dashboard/stats", {}, token),
      loadOperationalAlerts(token),
    ]).then(([statsResult, alertsResult]) => {
      if (statsResult.status === "rejected") {
        setError(statsResult.reason instanceof Error ? statsResult.reason.message : "Falha ao carregar o painel.");
        setStats(null);
      } else {
        setStats(statsResult.value);
        setError(null);
      }
      setAlerts(alertsResult.status === "fulfilled" ? alertsResult.value : []);
    }).finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    setTimelineLoading(true);
    request<ConversationTimeline>(`/dashboard/conversations-timeline?days=${period}`, {}, token)
      .then((value) => {
        setTimeline(value);
        setTimelineError(null);
      })
      .catch((reason) => setTimelineError(reason instanceof Error ? reason.message : "Falha ao carregar a linha do tempo."))
      .finally(() => setTimelineLoading(false));
  }, [period, token]);

  if (loading) return <section className="empty-state large" aria-live="polite">Carregando visão geral...</section>;
  if (error) return <section className="error-box" role="alert">{error}</section>;

  const contactsValue = contactKind === "all" ? stats?.contacts : stats?.contacts_by_kind[contactKind];

  return (
    <section className="page-stack">
      {(() => {
        const steps = stats ? firstSteps(stats, alerts) : [];
        const showSteps = steps.some((step) => !step.done);
        // While the checklist is on screen it already asks for WhatsApp; no need to say it twice.
        const visibleAlerts = showSteps ? alerts.filter((alert) => alert.key !== "whatsapp") : alerts;
        return (
          <>
            {showSteps ? <FirstSteps steps={steps} /> : null}
            {visibleAlerts.length ? (
              <Card className="health-card operational-warning" role="alert">
                <AlertTriangle size={18} />
                <ul className="alert-list">
                  {visibleAlerts.map((alert) => (
                    <li key={alert.key}>
                      <span>{alert.message}</span>
                      {alert.action ? (
                        <button className="link-button" onClick={() => openAppLink(alert.action!.href)} type="button">
                          {alert.action.label}
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </Card>
            ) : !showSteps ? (
              <p className="health-ok"><CheckCircle2 size={16} /> Tudo funcionando: nenhum alerta nas verificações.</p>
            ) : null}
          </>
        );
      })()}

      <div className="metric-grid">
        <article className="metric-card">
          <div className="metric-card-header">
            <span>Contatos</span>
            <div className="metric-icon"><Users size={18} /></div>
          </div>
          <strong>{formatNumber(contactsValue ?? "—")}</strong>
          <div className="metric-footer">
            <label className="metric-filter">
              <span className="sr-only">Tipo de contato</span>
              <select value={contactKind} onChange={(event) => setContactKind(event.target.value as ContactKind | "all")}>
                {contactKindOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>
        </article>
        <SimpleMetric icon={SearchCheck} label="Demandas de busca" value={stats?.search_demands} detail="Pedidos de imóvel registrados" />
        <SimpleMetric icon={Building2} label="Imóveis na carteira" value={stats?.properties} detail="Total cadastrado pela imobiliária" />
        <SimpleMetric icon={MessageSquare} label="Conversas iniciadas" value={stats?.conversations} detail="Pela IA ou por atendente" />
      </div>

      <Card>
        <div className="card-header timeline-header">
          <div>
            <h2>Conversas iniciadas por dia</h2>
            <p>
              {timeline
                ? `${formatNumber(timeline.total)} conversa(s) nos últimos ${timeline.days} dias, com IA ou humano.`
                : "Conversas abertas com IA ou atendimento humano."}
            </p>
          </div>
          <div className="period-filter" role="group" aria-label="Período">
            {periods.map((option) => (
              <button
                aria-pressed={period === option}
                className={period === option ? "filter-chip active" : "filter-chip"}
                key={option}
                onClick={() => setPeriod(option)}
                type="button"
              >
                {option}d
              </button>
            ))}
          </div>
        </div>
        {timelineError ? <div className="error-box">{timelineError}</div> : null}
        {timeline ? (
          <ConversationChart loading={timelineLoading} timeline={timeline} />
        ) : timelineLoading ? (
          <div className="empty-state" aria-live="polite">Carregando linha do tempo...</div>
        ) : null}
      </Card>
    </section>
  );
}

type Step = { key: string; label: string; detail: string; done: boolean; href: string; action: string };

function firstSteps(stats: DashboardStats, alerts: OperationalAlert[]): Step[] {
  const whatsappOk = !alerts.some((alert) => alert.key === "whatsapp" || alert.key === "whatsapp-unknown");
  return [
    {
      key: "whatsapp",
      label: "Conectar o WhatsApp",
      detail: "É por ele que os leads falam com o agente.",
      done: whatsappOk,
      href: "/configuracoes?aba=channels",
      action: "Conectar",
    },
    {
      key: "properties",
      label: "Cadastrar o primeiro imóvel",
      detail: "O agente só oferece o que está na carteira.",
      done: stats.properties > 0,
      href: "/imoveis",
      action: "Cadastrar",
    },
    {
      key: "conversation",
      label: "Receber a primeira conversa",
      detail: "Mande uma mensagem de teste para o número conectado.",
      done: stats.conversations > 0,
      href: "/conversas",
      action: "Abrir conversas",
    },
  ];
}

function FirstSteps({ steps }: { steps: Step[] }) {
  const done = steps.filter((step) => step.done).length;
  const next = steps.find((step) => !step.done);
  return (
    <Card className="first-steps">
      <div className="first-steps-header">
        <div>
          <h2>Primeiros passos</h2>
          <p>{done} de {steps.length} concluídos. Falta pouco para o agente começar a atender.</p>
        </div>
        <div className="first-steps-progress" aria-hidden="true">
          <span style={{ width: `${(done / steps.length) * 100}%` }} />
        </div>
      </div>
      <ol className="first-steps-list">
        {steps.map((step) => (
          <li className={step.done ? "done" : step === next ? "next" : undefined} key={step.key}>
            <span className="first-steps-mark">{step.done ? <Check size={14} /> : null}</span>
            <div>
              <strong>{step.label}</strong>
              <small>{step.detail}</small>
            </div>
            {!step.done ? (
              <button
                className={step === next ? "primary-button" : "secondary-button"}
                onClick={() => openAppLink(step.href)}
                type="button"
              >
                {step.action}
              </button>
            ) : null}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function SimpleMetric({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof Users;
  label: string;
  value: number | undefined;
  detail: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-card-header">
        <span>{label}</span>
        <div className="metric-icon"><Icon size={18} /></div>
      </div>
      <strong>{formatNumber(value ?? "—")}</strong>
      <div className="metric-footer"><small>{detail}</small></div>
    </article>
  );
}

const dayFormatter = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", timeZone: "UTC" });
const longDayFormatter = new Intl.DateTimeFormat("pt-BR", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  timeZone: "UTC",
});

function ConversationChart({ timeline, loading }: { timeline: ConversationTimeline; loading: boolean }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const max = Math.max(...timeline.points.map((point) => point.conversations), 0);
  const scaleMax = niceCeiling(max);
  const ticks = [scaleMax, scaleMax / 2, 0];
  const narrow = typeof window !== "undefined" && window.innerWidth < 640;
  const labelEvery = (timeline.days <= 7 ? 1 : timeline.days <= 30 ? 5 : 15) * (narrow && timeline.days > 7 ? 2 : 1);
  const hoveredPoint = hovered === null ? null : timeline.points[hovered];

  return (
    <div className={loading ? "timeline-chart refreshing" : "timeline-chart"}>
      <div className="timeline-plot">
        <div className="timeline-axis" aria-hidden="true">
          {ticks.map((tick) => <span key={tick}>{formatNumber(tick)}</span>)}
        </div>
        <div className="timeline-area">
          <div className="timeline-grid" aria-hidden="true">
            {ticks.map((tick) => <i key={tick} />)}
          </div>
          <div
            className="timeline-bars"
            onPointerLeave={() => setHovered(null)}
            style={{ gridTemplateColumns: `repeat(${timeline.points.length}, minmax(0, 1fr))` }}
          >
            {timeline.points.map((point, index) => (
              <button
                aria-label={`${longDayFormatter.format(new Date(point.date))}: ${point.conversations} conversa(s)`}
                className={hovered === index ? "timeline-bar active" : "timeline-bar"}
                key={point.date}
                onBlur={() => setHovered(null)}
                onFocus={() => setHovered(index)}
                onPointerEnter={() => setHovered(index)}
                type="button"
              >
                <span style={{ height: scaleMax ? `${(point.conversations / scaleMax) * 100}%` : "0%" }} />
              </button>
            ))}
          </div>
          {hoveredPoint && hovered !== null ? (
            <div
              className="timeline-tooltip"
              role="status"
              style={{ left: `${((hovered + 0.5) / timeline.points.length) * 100}%` }}
            >
              <strong>{formatNumber(hoveredPoint.conversations)}</strong>
              <span>{longDayFormatter.format(new Date(hoveredPoint.date))}</span>
            </div>
          ) : null}
        </div>
        <span aria-hidden="true" />
        <div
          className="timeline-labels"
          aria-hidden="true"
          style={{ gridTemplateColumns: `repeat(${timeline.points.length}, minmax(0, 1fr))` }}
        >
          {timeline.points.map((point, index) => (
            <span key={point.date}>
              {(timeline.points.length - 1 - index) % labelEvery === 0 ? dayFormatter.format(new Date(point.date)) : ""}
            </span>
          ))}
        </div>
      </div>
      <details className="timeline-table">
        <summary>Ver dados em tabela</summary>
        <table>
          <thead>
            <tr>
              <th>Dia</th>
              <th>Conversas iniciadas</th>
            </tr>
          </thead>
          <tbody>
            {timeline.points.map((point) => (
              <tr key={point.date}>
                <td>{longDayFormatter.format(new Date(point.date))}</td>
                <td>{formatNumber(point.conversations)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function niceCeiling(value: number) {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) {
    const candidate = step * magnitude;
    if (candidate >= value && candidate % 2 === 0) return candidate;
  }
  return 10 * magnitude;
}
