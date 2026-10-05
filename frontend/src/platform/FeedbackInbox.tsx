import { useEffect, useState } from "react";
import { request } from "../api/client";
import { Card } from "../components/Card";

type Report = {
  id: string;
  kind: "problem" | "suggestion" | "question" | "praise";
  message: string;
  page: string | null;
  status: "new" | "in_progress" | "resolved";
  admin_note: string | null;
  created_at: string;
  tenant_name: string;
  user_name: string | null;
  user_email: string | null;
  contact_phone: string | null;
  user_agent: string | null;
};

const KIND_LABELS: Record<Report["kind"], string> = { problem: "Problema", suggestion: "Sugestão", question: "Dúvida", praise: "Elogio" };
const STATUS_LABELS: Record<Report["status"], string> = { new: "Novo", in_progress: "Em andamento", resolved: "Resolvido" };
const FILTERS: Array<{ value: "" | Report["status"]; label: string }> = [
  { value: "new", label: "Novos" },
  { value: "in_progress", label: "Em andamento" },
  { value: "resolved", label: "Resolvidos" },
  { value: "", label: "Todos" },
];

/** What the beta testers sent from inside the app. */
export function FeedbackInbox({ token }: { token: string }) {
  const [filter, setFilter] = useState<"" | Report["status"]>("new");
  const [reports, setReports] = useState<Report[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReports(null);
    request<Report[]>(`/platform/feedback${filter ? `?status=${filter}` : ""}`, {}, token)
      .then(setReports)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Falha ao carregar."));
  }, [filter, token]);

  async function update(report: Report, patch: Partial<Pick<Report, "status" | "admin_note">>) {
    try {
      const updated = await request<Report>(`/platform/feedback/${report.id}`, { method: "PATCH", body: JSON.stringify(patch) }, token);
      setReports((current) =>
        (current ?? []).map((item) => (item.id === updated.id ? updated : item)).filter((item) => !filter || item.status === filter),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível atualizar.");
    }
  }

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Feedback dos clientes</h2>
          <p>Problemas, sugestões e dúvidas enviados pelo botão "Enviar feedback" do painel.</p>
        </div>
      </div>
      <div className="period-filter" role="group" aria-label="Filtrar">
        {FILTERS.map((item) => (
          <button aria-pressed={filter === item.value} className={filter === item.value ? "filter-chip active" : "filter-chip"} key={item.label} onClick={() => setFilter(item.value)} type="button">
            {item.label}
          </button>
        ))}
      </div>
      {error ? <div className="error-box" role="alert">{error}</div> : null}
      {reports === null && !error ? <div className="empty-state">Carregando…</div> : null}
      {reports?.length === 0 ? <div className="empty-state">Nada por aqui.</div> : null}
      <ol className="feedback-list">
        {reports?.map((report) => (
          <li key={report.id}>
            <div className="feedback-head">
              <span className={`connection-state ${report.kind === "problem" ? "state-pending" : "state-soon"}`}>{KIND_LABELS[report.kind]}</span>
              <strong>{report.tenant_name}</strong>
              <small>{new Date(report.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</small>
            </div>
            <p className="feedback-message">{report.message}</p>
            <small className="feedback-meta">
              {[report.user_name, report.user_email, report.contact_phone && `WhatsApp ${report.contact_phone}`, report.page && `tela ${report.page}`].filter(Boolean).join(" · ")}
            </small>
            <div className="feedback-actions">
              <select aria-label="Situação" onChange={(event) => void update(report, { status: event.target.value as Report["status"] })} value={report.status}>
                {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <input
                aria-label="Anotação interna"
                defaultValue={report.admin_note ?? ""}
                onBlur={(event) => {
                  if ((event.target.value || null) !== report.admin_note) void update(report, { admin_note: event.target.value });
                }}
                placeholder="Anotação interna (salva ao sair do campo)"
              />
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
