import { useEffect, useState } from "react";
import { request } from "../api/client";
import type { LeadDemand } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { DataTable } from "../components/DataTable";
import { formatCurrency } from "../lib/format";

type LeadForm = {
  lead_name: string;
  phone: string;
  purpose: string;
  property_type: string;
  city: string;
  neighborhoods: string;
  price_min: string;
  price_max: string;
  bedrooms: string;
  parking_spaces: string;
  notes: string;
};

const emptyLeadForm: LeadForm = {
  lead_name: "",
  phone: "",
  purpose: "buy",
  property_type: "",
  city: "",
  neighborhoods: "",
  price_min: "",
  price_max: "",
  bedrooms: "",
  parking_spaces: "",
  notes: "",
};

export function LeadsPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<LeadDemand[]>([]);
  const [form, setForm] = useState<LeadForm>(emptyLeadForm);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadDemands() {
    setItems(await request<LeadDemand[]>("/leads/demands", {}, token));
  }

  useEffect(() => {
    void loadDemands();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function createDemand() {
    setLoading(true);
    setMessage(null);
    try {
      await request<LeadDemand>(
        "/leads/demands",
        {
          method: "POST",
          body: JSON.stringify({
            ...form,
            neighborhoods: form.neighborhoods
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            price_min: form.price_min || null,
            price_max: form.price_max || null,
            bedrooms: form.bedrooms ? Number(form.bedrooms) : null,
            parking_spaces: form.parking_spaces ? Number(form.parking_spaces) : null,
            notes: form.notes || null,
          }),
        },
        token,
      );
      setForm(emptyLeadForm);
      setMessage("Demanda criada.");
      await loadDemands();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao criar demanda.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-header">
        <span className="eyebrow">SDR</span>
        <h1>Demandas</h1>
        <p>Demandas criadas pela IA ou pela operação.</p>
      </header>
      <article className="card settings-panel-card">
        <div className="settings-panel-header">
          <div>
            <h2>Nova demanda</h2>
            <p>Crie uma demanda manual para iniciar captação e matching.</p>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Lead
            <input
              value={form.lead_name}
              onChange={(event) => setForm((current) => ({ ...current, lead_name: event.target.value }))}
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
            Finalidade
            <select
              value={form.purpose}
              onChange={(event) => setForm((current) => ({ ...current, purpose: event.target.value }))}
            >
              <option value="buy">Compra</option>
              <option value="rent">Locação</option>
            </select>
          </label>
          <label>
            Tipo
            <input
              value={form.property_type}
              onChange={(event) =>
                setForm((current) => ({ ...current, property_type: event.target.value }))
              }
            />
          </label>
          <label>
            Cidade
            <input
              value={form.city}
              onChange={(event) => setForm((current) => ({ ...current, city: event.target.value }))}
            />
          </label>
          <label>
            Bairros
            <input
              value={form.neighborhoods}
              onChange={(event) =>
                setForm((current) => ({ ...current, neighborhoods: event.target.value }))
              }
              placeholder="Centro, Hamburgo Velho"
            />
          </label>
          <label>
            Preço mínimo
            <input
              value={form.price_min}
              onChange={(event) =>
                setForm((current) => ({ ...current, price_min: event.target.value }))
              }
            />
          </label>
          <label>
            Preço máximo
            <input
              value={form.price_max}
              onChange={(event) =>
                setForm((current) => ({ ...current, price_max: event.target.value }))
              }
            />
          </label>
          <label>
            Quartos
            <input
              value={form.bedrooms}
              onChange={(event) => setForm((current) => ({ ...current, bedrooms: event.target.value }))}
            />
          </label>
          <label>
            Vagas
            <input
              value={form.parking_spaces}
              onChange={(event) =>
                setForm((current) => ({ ...current, parking_spaces: event.target.value }))
              }
            />
          </label>
          <label className="form-span-2">
            Observações
            <textarea
              value={form.notes}
              onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
            />
          </label>
        </div>
        <div className="settings-actions">
          {message ? <span>{message}</span> : null}
          <button disabled={loading} onClick={createDemand} type="button">
            {loading ? "Criando..." : "Criar demanda"}
          </button>
        </div>
      </article>
      <DataTable
        data={items}
        empty="Nenhuma demanda cadastrada."
        columns={[
          { key: "lead", label: "Lead", render: (item) => item.lead_name },
          { key: "phone", label: "Telefone", render: (item) => item.phone },
          { key: "purpose", label: "Finalidade", render: (item) => item.purpose ?? "—" },
          { key: "city", label: "Cidade", render: (item) => item.city ?? "—" },
          {
            key: "budget",
            label: "Orçamento",
            render: (item) => `${formatCurrency(item.price_min)} a ${formatCurrency(item.price_max)}`,
          },
          { key: "status", label: "Status", render: (item) => <Badge>{item.status}</Badge> },
        ]}
      />
    </section>
  );
}
