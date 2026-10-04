import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { Card } from "../../components/Card";
import { formatCurrency, formatPhone } from "../../lib/format";

type Activity = {
  id: string;
  actor_type: "user" | "system";
  actor_name: string | null;
  entity: string;
  action: string;
  summary: string;
  snapshot: Record<string, unknown>;
  created_at: string;
};

const FILTERS = [
  { value: "", label: "Tudo" },
  { value: "lead_demand", label: "Demandas" },
  { value: "property", label: "Imóveis" },
  { value: "contact", label: "Contatos" },
  { value: "knowledge_document", label: "Documentos" },
];

const ACTION_LABELS: Record<string, string> = {
  deleted: "Excluído",
  merged: "Juntado",
  closed: "Encerrado",
};

// Fields worth showing from the copy of a removed record, in reading order.
const SNAPSHOT_FIELDS: Array<[string, string, (value: unknown) => string]> = [
  ["lead_name", "Lead", String],
  ["name", "Nome", String],
  ["title", "Imóvel", String],
  ["filename", "Arquivo", String],
  ["phone", "Telefone", (value) => formatPhone(String(value))],
  ["email", "E-mail", String],
  ["purpose", "Finalidade", (value) => ({ buy: "Compra", rent: "Aluguel" })[String(value)] ?? String(value)],
  ["property_type", "Tipo", String],
  ["city", "Cidade", String],
  ["neighborhoods", "Bairros", (value) => (Array.isArray(value) ? value.join(", ") : String(value))],
  ["price_min", "Valor mínimo", (value) => formatCurrency(Number(value))],
  ["price_max", "Valor máximo", (value) => formatCurrency(Number(value))],
  ["bedrooms", "Quartos", String],
  ["interest", "Interesse", String],
  ["notes", "Observações", String],
  ["created_at", "Criado em", (value) => new Date(String(value)).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })],
];

/** What was removed or merged, by whom and when, with a readable copy of the record. */
export function ActivitySettingsPanel() {
  const { token } = useAuth();
  const [entity, setEntity] = useState("");
  const [items, setItems] = useState<Activity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setItems(null);
    request<Activity[]>(`/activity${entity ? `?entity=${entity}` : ""}`, {}, token)
      .then((value) => {
        setItems(value);
        setError(null);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Falha ao carregar o histórico."));
  }, [entity, token]);

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Histórico</h2>
          <p>Exclusões e ajustes automáticos nos registros da imobiliária, com quem fez e uma cópia do que foi removido.</p>
        </div>
      </div>
      <div className="period-filter activity-filters" role="group" aria-label="Filtrar histórico">
        {FILTERS.map((filter) => (
          <button
            aria-pressed={entity === filter.value}
            className={entity === filter.value ? "filter-chip active" : "filter-chip"}
            key={filter.value}
            onClick={() => setEntity(filter.value)}
            type="button"
          >
            {filter.label}
          </button>
        ))}
      </div>
      {error ? <div className="error-box" role="alert">{error}</div> : null}
      {!items && !error ? <div className="empty-state" aria-live="polite"><Loader2 className="spin" size={16} /> Carregando histórico...</div> : null}
      {items?.length === 0 ? <div className="empty-state">Nada registrado por aqui ainda.</div> : null}
      {items?.length ? (
        <ol className="activity-list">
          {items.map((item) => {
            const facts = SNAPSHOT_FIELDS.filter(([key]) => item.snapshot[key] != null && item.snapshot[key] !== "" && !(Array.isArray(item.snapshot[key]) && !(item.snapshot[key] as unknown[]).length));
            return (
              <li key={item.id}>
                <div className="activity-head">
                  <span className={`connection-state ${item.action === "deleted" ? "state-pending" : "state-soon"}`}>
                    {ACTION_LABELS[item.action] ?? item.action}
                  </span>
                  <time dateTime={item.created_at}>
                    {new Date(item.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
                  </time>
                </div>
                <strong>{item.summary}</strong>
                <small>{item.actor_type === "system" ? "Feito automaticamente pelo sistema" : `Por ${item.actor_name ?? "usuário removido"}`}</small>
                {facts.length ? (
                  <details>
                    <summary>Ver o que foi {item.action === "merged" ? "juntado" : "removido"}</summary>
                    <dl className="activity-snapshot">
                      {facts.map(([key, label, format]) => (
                        <div key={key}>
                          <dt>{label}</dt>
                          <dd>{format(item.snapshot[key])}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}
    </Card>
  );
}
