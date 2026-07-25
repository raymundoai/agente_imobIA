import { useEffect, useState } from "react";
import { request } from "../api/client";
import type { MaintenanceTicket } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { DataTable } from "../components/DataTable";

type TicketForm = {
  customer_name: string;
  phone: string;
  property_reference: string;
  issue_type: string;
  description: string;
  urgency: string;
};

const emptyTicket: TicketForm = {
  customer_name: "",
  phone: "",
  property_reference: "",
  issue_type: "",
  description: "",
  urgency: "medium",
};

export function MaintenancePage() {
  const { token } = useAuth();
  const [items, setItems] = useState<MaintenanceTicket[]>([]);
  const [form, setForm] = useState<TicketForm>(emptyTicket);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadTickets() {
    setItems(await request<MaintenanceTicket[]>("/maintenance/tickets", {}, token));
  }

  useEffect(() => {
    void loadTickets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function createTicket() {
    setLoading(true);
    setMessage(null);
    try {
      await request<MaintenanceTicket>(
        "/maintenance/tickets",
        {
          method: "POST",
          body: JSON.stringify({
            ...form,
            property_reference: form.property_reference || null,
          }),
        },
        token,
      );
      setForm(emptyTicket);
      setMessage("Chamado criado.");
      await loadTickets();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao criar chamado.");
    } finally {
      setLoading(false);
    }
  }

  async function updateStatus(ticket: MaintenanceTicket, status: string) {
    try {
      const updated = await request<MaintenanceTicket>(
        `/maintenance/tickets/${ticket.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ status }),
        },
        token,
      );
      setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao atualizar chamado.");
    }
  }

  return (
    <section className="page-stack">
      <header className="page-header">
        <span className="eyebrow">Pós-contrato</span>
        <h1>Manutenção</h1>
        <p>Chamados criados pela IA ou pela operação interna.</p>
      </header>
      <article className="card settings-panel-card">
        <div className="settings-panel-header">
          <div>
            <h2>Novo chamado</h2>
            <p>Registro manual de manutenção para complementar o fluxo da IA.</p>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Cliente
            <input
              value={form.customer_name}
              onChange={(event) =>
                setForm((current) => ({ ...current, customer_name: event.target.value }))
              }
            />
          </label>
          <label>
            Telefone
            <input
              value={form.phone}
              onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))}
            />
          </label>
          <label>
            Referência do imóvel
            <input
              value={form.property_reference}
              onChange={(event) =>
                setForm((current) => ({ ...current, property_reference: event.target.value }))
              }
            />
          </label>
          <label>
            Tipo de problema
            <input
              value={form.issue_type}
              onChange={(event) =>
                setForm((current) => ({ ...current, issue_type: event.target.value }))
              }
            />
          </label>
          <label>
            Urgência
            <select
              value={form.urgency}
              onChange={(event) => setForm((current) => ({ ...current, urgency: event.target.value }))}
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
          </label>
          <label className="form-span-2">
            Descrição
            <textarea
              value={form.description}
              onChange={(event) =>
                setForm((current) => ({ ...current, description: event.target.value }))
              }
            />
          </label>
        </div>
        <div className="settings-actions">
          {message ? <span>{message}</span> : null}
          <button disabled={loading} onClick={createTicket} type="button">
            {loading ? "Criando..." : "Criar chamado"}
          </button>
        </div>
      </article>
      <DataTable
        data={items}
        empty="Nenhum chamado aberto."
        columns={[
          { key: "customer", label: "Cliente", render: (item) => item.customer_name },
          { key: "issue", label: "Problema", render: (item) => item.issue_type },
          {
            key: "urgency",
            label: "Urgência",
            render: (item) => (
              <Badge variant={item.urgency === "critical" ? "danger" : "accent"}>{item.urgency}</Badge>
            ),
          },
          {
            key: "status",
            label: "Status",
            render: (item) => (
              <select
                value={item.status}
                onChange={(event) => void updateStatus(item, event.target.value)}
              >
                <option value="open">open</option>
                <option value="in_progress">in_progress</option>
                <option value="resolved">resolved</option>
              </select>
            ),
          },
        ]}
      />
    </section>
  );
}
