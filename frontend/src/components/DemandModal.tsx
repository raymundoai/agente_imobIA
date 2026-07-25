import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../api/client";
import type { LeadDemand } from "../api/types";
import { useAuth } from "../auth/AuthContext";

type DemandForm = {
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
  min_area: string;
  notes: string;
};

type DemandModalProps = {
  initialLeadName?: string | null;
  initialPhone?: string | null;
  isOpen: boolean;
  onClose: () => void;
  onCreated: (demand: LeadDemand) => void;
};

const emptyForm: DemandForm = {
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
  min_area: "",
  notes: "",
};

const brlFormatter = new Intl.NumberFormat("pt-BR", {
  currency: "BRL",
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
  style: "currency",
});

function formatPhoneInput(value: string) {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  if (digits.length <= 2) return digits ? `(${digits}` : "";
  if (digits.length <= 7) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
  return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
}

function formatCurrencyInput(value: string) {
  const digits = value.replace(/\D/g, "");
  return digits ? brlFormatter.format(Number(digits) / 100) : "";
}

function parseCurrencyInput(value: string) {
  const digits = value.replace(/\D/g, "");
  return digits ? (Number(digits) / 100).toFixed(2) : null;
}

export function DemandModal({
  initialLeadName,
  initialPhone,
  isOpen,
  onClose,
  onCreated,
}: DemandModalProps) {
  const { token } = useAuth();
  const [form, setForm] = useState<DemandForm>(emptyForm);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setForm({
      ...emptyForm,
      lead_name: initialLeadName ?? "",
      phone: formatPhoneInput(initialPhone ?? ""),
    });
    setMessage(null);
  }, [initialLeadName, initialPhone, isOpen]);

  if (!isOpen) {
    return null;
  }

  const phoneDigits = form.phone.replace(/\D/g, "");
  const priceMin = parseCurrencyInput(form.price_min);
  const priceMax = parseCurrencyInput(form.price_max);
  const priceRangeValid = !priceMin || !priceMax || Number(priceMin) <= Number(priceMax);
  const isFormValid = Boolean(
    form.lead_name.trim() &&
      phoneDigits.length === 11 &&
      form.purpose &&
      form.property_type.trim() &&
      form.city.trim() &&
      form.neighborhoods.split(",").some((item) => item.trim()) &&
      priceMax &&
      priceRangeValid,
  );

  async function createDemand() {
    setSaving(true);
    setMessage(null);
    try {
      const demand = await request<LeadDemand>(
        "/leads/demands",
        {
          method: "POST",
          body: JSON.stringify({
            lead_name: form.lead_name,
            phone: phoneDigits,
            purpose: form.purpose || null,
            property_type: form.property_type || null,
            city: form.city || null,
            neighborhoods: form.neighborhoods
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            price_min: parseCurrencyInput(form.price_min),
            price_max: parseCurrencyInput(form.price_max),
            bedrooms: form.bedrooms ? Number(form.bedrooms) : null,
            parking_spaces: form.parking_spaces ? Number(form.parking_spaces) : null,
            min_area: form.min_area ? Number(form.min_area) : null,
            notes: form.notes || null,
          }),
        },
        token,
      );
      onCreated(demand);
      onClose();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao cadastrar demanda.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-modal="true" className="demand-modal" role="dialog">
        <header className="modal-header">
          <div>
            <span className="eyebrow">Busca de imóvel</span>
            <h2>Cadastrar demanda</h2>
            <p>Preencha o perfil do imóvel para registrar a demanda e iniciar a busca.</p>
            <small className="required-fields-note">Campos marcados com * são obrigatórios.</small>
          </div>
          <button aria-label="Fechar" className="icon-button" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </header>

        <div className="form-grid">
          <label>
            Cliente *
            <input
              required
              value={form.lead_name}
              onChange={(event) => setForm((current) => ({ ...current, lead_name: event.target.value }))}
            />
          </label>
          <label>
            Telefone *
            <input
              inputMode="tel"
              maxLength={15}
              placeholder="(00) 00000-0000"
              required
              value={form.phone}
              onChange={(event) =>
                setForm((current) => ({ ...current, phone: formatPhoneInput(event.target.value) }))
              }
            />
            {form.phone && phoneDigits.length < 11 ? <small>Informe DDD e celular com 9 dígitos.</small> : null}
          </label>
          <label>
            Finalidade *
            <select
              required
              value={form.purpose}
              onChange={(event) => setForm((current) => ({ ...current, purpose: event.target.value }))}
            >
              <option value="buy">Comprar</option>
              <option value="rent">Alugar</option>
            </select>
          </label>
          <label>
            Tipo de imóvel *
            <input
              required
              value={form.property_type}
              onChange={(event) =>
                setForm((current) => ({ ...current, property_type: event.target.value }))
              }
              placeholder="Apartamento, casa, sala comercial"
            />
          </label>
          <label>
            Cidade *
            <input
              required
              value={form.city}
              onChange={(event) => setForm((current) => ({ ...current, city: event.target.value }))}
            />
          </label>
          <label>
            Bairros *
            <input
              required
              value={form.neighborhoods}
              onChange={(event) =>
                setForm((current) => ({ ...current, neighborhoods: event.target.value }))
              }
              placeholder="Centro, Hamburgo Velho"
            />
          </label>
          <label>
            Valor mínimo
            <input
              inputMode="decimal"
              placeholder="R$ 500.000,00"
              value={form.price_min}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  price_min: formatCurrencyInput(event.target.value),
                }))
              }
            />
          </label>
          <label>
            Valor máximo *
            <input
              inputMode="decimal"
              placeholder="R$ 900.000,00"
              required
              value={form.price_max}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  price_max: formatCurrencyInput(event.target.value),
                }))
              }
            />
            {!priceRangeValid ? <small>O valor máximo deve ser maior que o mínimo.</small> : null}
          </label>
          <label>
            Quartos
            <input
              inputMode="numeric"
              value={form.bedrooms}
              onChange={(event) => setForm((current) => ({ ...current, bedrooms: event.target.value }))}
            />
          </label>
          <label>
            Vagas
            <input
              inputMode="numeric"
              value={form.parking_spaces}
              onChange={(event) =>
                setForm((current) => ({ ...current, parking_spaces: event.target.value }))
              }
            />
          </label>
          <label>
            Área mínima
            <input
              inputMode="numeric"
              value={form.min_area}
              onChange={(event) => setForm((current) => ({ ...current, min_area: event.target.value }))}
            />
          </label>
          <label className="form-span-2">
            Observações
            <textarea
              value={form.notes}
              onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
              placeholder="Preferências, urgência, restrições e informações combinadas na conversa."
            />
          </label>
        </div>

        <footer className="modal-actions">
          {message ? <span>{message}</span> : null}
          <button className="button-outline" onClick={onClose} type="button">
            Cancelar
          </button>
          <button
            disabled={saving || !isFormValid}
            onClick={createDemand}
            type="button"
          >
            <Search size={16} />
            {saving ? "Iniciando..." : "Iniciar busca"}
          </button>
        </footer>
      </section>
    </div>
  );
}
