import { ImagePlus, Plus, X } from "lucide-react";
import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { request } from "../api/client";
import type { Property } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { PropertyCard } from "../components/PropertyCard";

type PropertyForm = {
  listing_code: string;
  title: string;
  purpose: string;
  property_type: string;
  category: string;
  street: string;
  number: string;
  complement: string;
  state: string;
  postal_code: string;
  city: string;
  neighborhood: string;
  sale_price: string;
  rent_price: string;
  condo_fee: string;
  property_tax: string;
  bedrooms: string;
  suites: string;
  bathrooms: string;
  parking_spaces: string;
  area: string;
  land_area: string;
  description: string;
  rooms: string;
  amenities: string;
  pet_friendly: boolean;
  furnished: boolean;
  accepts_financing: boolean;
  accepts_exchange: boolean;
  rental_guarantees: string;
  advertiser_name: string;
  advertiser_phone: string;
  source_url: string;
};

type PropertyPhoto = {
  id: string;
  file: File;
  previewUrl: string;
};

const imageOptimizationOptions = [
  { id: "lighting", label: "Melhorar iluminação" },
  { id: "straighten", label: "Corrigir enquadramento" },
  { id: "declutter", label: "Remover móveis e utensílios" },
  { id: "walls", label: "Suavizar marcas em paredes" },
  { id: "windows", label: "Realçar vista e janelas" },
  { id: "sharpen", label: "Aumentar nitidez" },
];

const brlInputFormatter = new Intl.NumberFormat("pt-BR", {
  currency: "BRL",
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
  style: "currency",
});

const initialPropertyForm: PropertyForm = {
  listing_code: "",
  title: "",
  purpose: "buy",
  property_type: "apartamento",
  category: "residential",
  street: "",
  number: "",
  complement: "",
  state: "SP",
  postal_code: "",
  city: "",
  neighborhood: "",
  sale_price: "",
  rent_price: "",
  condo_fee: "",
  property_tax: "",
  bedrooms: "",
  suites: "",
  bathrooms: "",
  parking_spaces: "",
  area: "",
  land_area: "",
  description: "",
  rooms: "",
  amenities: "",
  pet_friendly: false,
  furnished: false,
  accepts_financing: false,
  accepts_exchange: false,
  rental_guarantees: "",
  advertiser_name: "",
  advertiser_phone: "",
  source_url: "",
};

function toNullableNumber(value: string) {
  const parsed = Number(value);
  return value.trim() && Number.isFinite(parsed) ? parsed : null;
}

function formatCurrencyInput(value: string) {
  const digits = value.replace(/\D/g, "");

  if (!digits) {
    return "";
  }

  return brlInputFormatter.format(Number(digits) / 100);
}

function parseCurrencyInput(value: string) {
  const digits = value.replace(/\D/g, "");

  if (!digits) {
    return "";
  }

  return (Number(digits) / 100).toFixed(2);
}

function splitList(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function PropertiesPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<Property[]>([]);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [form, setForm] = useState<PropertyForm>(initialPropertyForm);
  const [photos, setPhotos] = useState<PropertyPhoto[]>([]);
  const [imageOptimizations, setImageOptimizations] = useState<string[]>([]);
  const [imageOptimizationNote, setImageOptimizationNote] = useState("");
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void request<Property[]>("/properties", {}, token).then((properties) =>
      setItems(properties),
    );
  }, [token]);

  function updateForm(field: keyof PropertyForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function closeCreateModal() {
    photos.forEach((photo) => URL.revokeObjectURL(photo.previewUrl));
    setPhotos([]);
    setImageOptimizations([]);
    setImageOptimizationNote("");
    setForm(initialPropertyForm);
    setFormMessage(null);
    setIsCreateModalOpen(false);
  }

  function handlePhotoUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);

    if (!files.length) {
      return;
    }

    setPhotos((current) => [
      ...current,
      ...files.map((file) => ({
        id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`,
        file,
        previewUrl: URL.createObjectURL(file),
      })),
    ]);
    event.target.value = "";
  }

  function removePhoto(photoId: string) {
    setPhotos((current) => {
      const photo = current.find((item) => item.id === photoId);
      if (photo) {
        URL.revokeObjectURL(photo.previewUrl);
      }
      return current.filter((item) => item.id !== photoId);
    });
  }

  function toggleImageOptimization(optionId: string) {
    setImageOptimizations((current) =>
      current.includes(optionId) ? current.filter((item) => item !== optionId) : [...current, optionId],
    );
  }

  async function handleCreateProperty(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormMessage(null);

    let images: Array<Record<string, unknown>> = [];
    try {
      if (photos.length > 0) {
        const body = new FormData();
        photos.forEach((photo) => body.append("files", photo.file));
        body.append("optimizations", JSON.stringify(imageOptimizations));
        body.append("note", imageOptimizationNote.trim());
        const uploaded = await request<
          Array<Record<string, unknown>> | { images: Array<Record<string, unknown>> }
        >("/properties/images", { method: "POST", body }, token);
        images = Array.isArray(uploaded) ? uploaded : uploaded.images;
      }

      const payload = {
      listing_code: form.listing_code.trim() || null,
      title: form.title.trim(),
      purpose: form.purpose,
      property_type: form.property_type,
      category: form.category,
      sale_price: parseCurrencyInput(form.sale_price) || null,
      rent_price: parseCurrencyInput(form.rent_price) || null,
      description: form.description.trim() || null,
      bedrooms: toNullableNumber(form.bedrooms),
      suites: toNullableNumber(form.suites),
      bathrooms: toNullableNumber(form.bathrooms),
      parking_spaces: toNullableNumber(form.parking_spaces),
      area: toNullableNumber(form.area),
      land_area: toNullableNumber(form.land_area),
      address: {
        street: form.street.trim(),
        number: form.number.trim() || null,
        complement: form.complement.trim() || null,
        neighborhood: form.neighborhood.trim(),
        city: form.city.trim(),
        state: form.state.trim().toUpperCase(),
        postal_code: form.postal_code.trim() || null,
      },
      details: {
        condo_fee: parseCurrencyInput(form.condo_fee) || null,
        property_tax: parseCurrencyInput(form.property_tax) || null,
        pet_friendly: form.pet_friendly,
        furnished: form.furnished,
        accepts_financing: form.accepts_financing,
        accepts_exchange: form.accepts_exchange,
        rental_guarantees: splitList(form.rental_guarantees),
        rooms: splitList(form.rooms),
        amenities: splitList(form.amenities),
      },
      images,
      owner_name: form.advertiser_name.trim() || null,
      owner_phone: form.advertiser_phone.trim() || null,
      source_url: form.source_url.trim() || null,
    };
      const created = await request<Property>("/properties", {
        method: "POST",
        body: JSON.stringify(payload),
      }, token);
      setItems((current) => [created, ...current]);
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "Falha ao salvar imóvel.");
      setSaving(false);
      return;
    }
    photos.forEach((photo) => URL.revokeObjectURL(photo.previewUrl));
    setForm(initialPropertyForm);
    setPhotos([]);
    setImageOptimizations([]);
    setImageOptimizationNote("");
    setIsCreateModalOpen(false);
    setSaving(false);
  }

  return (
    <section className="page-stack properties-page">
      <div className="property-toolbar">
        <h2>Carteira de imóveis</h2>
        <div className="toolbar-actions">
          <button className="button-outline" onClick={() => setIsCreateModalOpen(true)} type="button">
            <Plus size={15} />
            Cadastrar Imóvel
          </button>
        </div>
      </div>

      {items.length > 0 ? (
        <div className="property-grid">
          {items.map((property) => (
            <PropertyCard key={property.id} property={property} />
          ))}
        </div>
      ) : (
        <div className="empty-state large">
          Nenhum imóvel cadastrado.
        </div>
      )}

      {isCreateModalOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section aria-modal="true" className="demand-modal property-modal" role="dialog">
            <div className="modal-header">
              <div>
                <h2>Cadastrar imóvel</h2>
                <p>Adicione um imóvel próprio para atendimento e recomendações.</p>
              </div>
              <button className="icon-button" onClick={closeCreateModal} type="button">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateProperty}>
              <div className="form-grid">
                <label className="form-span-2">
                  Título do imóvel
                  <input
                    onChange={(event) => updateForm("title", event.target.value)}
                    required
                    value={form.title}
                  />
                </label>
                <label>
                  Código do imóvel
                  <input onChange={(event) => updateForm("listing_code", event.target.value)} value={form.listing_code} />
                </label>
                <label>
                  Finalidade
                  <select onChange={(event) => updateForm("purpose", event.target.value)} value={form.purpose}>
                    <option value="buy">Venda</option>
                    <option value="rent">Locação</option>
                    <option value="both">Venda e locação</option>
                  </select>
                </label>
                <label>
                  Categoria
                  <select onChange={(event) => updateForm("category", event.target.value)} value={form.category}>
                    <option value="residential">Residencial</option>
                    <option value="commercial">Comercial</option>
                    <option value="mixed">Residencial e comercial</option>
                  </select>
                </label>
                <label>
                  Tipo
                  <select
                    onChange={(event) => updateForm("property_type", event.target.value)}
                    value={form.property_type}
                  >
                    <option value="apartamento">Apartamento</option>
                    <option value="casa">Casa</option>
                    <option value="sobrado">Sobrado</option>
                    <option value="studio">Studio</option>
                    <option value="kitnet">Kitnet</option>
                    <option value="loft">Loft</option>
                    <option value="cobertura">Cobertura</option>
                    <option value="terreno">Terreno</option>
                    <option value="chacara">Chácara</option>
                    <option value="sitio">Sítio</option>
                    <option value="fazenda">Fazenda</option>
                    <option value="sala_comercial">Sala comercial</option>
                    <option value="loja">Loja</option>
                    <option value="galpao">Galpão</option>
                    <option value="predio">Prédio</option>
                  </select>
                </label>
                <label className="form-span-2">
                  Logradouro
                  <input onChange={(event) => updateForm("street", event.target.value)} required value={form.street} />
                </label>
                <label>
                  Número
                  <input onChange={(event) => updateForm("number", event.target.value)} value={form.number} />
                </label>
                <label>
                  Complemento
                  <input onChange={(event) => updateForm("complement", event.target.value)} value={form.complement} />
                </label>
                <label>
                  Cidade
                  <input onChange={(event) => updateForm("city", event.target.value)} required value={form.city} />
                </label>
                <label>
                  Bairro
                  <input onChange={(event) => updateForm("neighborhood", event.target.value)} required value={form.neighborhood} />
                </label>
                <label>
                  UF
                  <input maxLength={2} onChange={(event) => updateForm("state", event.target.value)} required value={form.state} />
                </label>
                <label>
                  CEP
                  <input onChange={(event) => updateForm("postal_code", event.target.value)} value={form.postal_code} />
                </label>
                {form.purpose !== "rent" ? <label>
                  Valor de venda
                  <input
                    inputMode="numeric"
                    onChange={(event) => updateForm("sale_price", formatCurrencyInput(event.target.value))}
                    placeholder="R$ 850.000,00"
                    required
                    value={form.sale_price}
                  />
                </label> : null}
                {form.purpose !== "buy" ? <label>
                  Aluguel mensal
                  <input inputMode="numeric" onChange={(event) => updateForm("rent_price", formatCurrencyInput(event.target.value))} required value={form.rent_price} />
                </label> : null}
                <label>
                  Condomínio
                  <input inputMode="numeric" onChange={(event) => updateForm("condo_fee", formatCurrencyInput(event.target.value))} value={form.condo_fee} />
                </label>
                <label>
                  IPTU
                  <input inputMode="numeric" onChange={(event) => updateForm("property_tax", formatCurrencyInput(event.target.value))} value={form.property_tax} />
                </label>
                <label>
                  Área
                  <input
                    inputMode="numeric"
                    onChange={(event) => updateForm("area", event.target.value)}
                    placeholder="m²"
                    value={form.area}
                  />
                </label>
                <label>
                  Quartos
                  <input
                    inputMode="numeric"
                    onChange={(event) => updateForm("bedrooms", event.target.value)}
                    value={form.bedrooms}
                  />
                </label>
                <label>
                  Suítes
                  <input inputMode="numeric" onChange={(event) => updateForm("suites", event.target.value)} value={form.suites} />
                </label>
                <label>
                  Banheiros
                  <input inputMode="numeric" onChange={(event) => updateForm("bathrooms", event.target.value)} value={form.bathrooms} />
                </label>
                <label>
                  Vagas
                  <input
                    inputMode="numeric"
                    onChange={(event) => updateForm("parking_spaces", event.target.value)}
                    value={form.parking_spaces}
                  />
                </label>
                <label>
                  Área do terreno
                  <input inputMode="numeric" onChange={(event) => updateForm("land_area", event.target.value)} placeholder="m²" value={form.land_area} />
                </label>
                <label>
                  Proprietário
                  <input
                    onChange={(event) => updateForm("advertiser_name", event.target.value)}
                    value={form.advertiser_name}
                  />
                </label>
                <label className="form-span-2">
                  Sobre o imóvel
                  <textarea onChange={(event) => updateForm("description", event.target.value)} rows={5} value={form.description} />
                </label>
                <label className="form-span-2">
                  Ambientes
                  <input onChange={(event) => updateForm("rooms", event.target.value)} placeholder="Sala de jantar, cozinha, varanda, área de serviço" value={form.rooms} />
                </label>
                <label className="form-span-2">
                  Comodidades
                  <input onChange={(event) => updateForm("amenities", event.target.value)} placeholder="Piscina, churrasqueira, sauna, hidromassagem" value={form.amenities} />
                </label>
                <label>
                  <input checked={form.pet_friendly} onChange={(event) => setForm((current) => ({ ...current, pet_friendly: event.target.checked }))} type="checkbox" />
                  Aceita pet
                </label>
                <label>
                  <input checked={form.furnished} onChange={(event) => setForm((current) => ({ ...current, furnished: event.target.checked }))} type="checkbox" />
                  Mobiliado
                </label>
                {form.purpose !== "rent" ? <>
                  <label><input checked={form.accepts_financing} onChange={(event) => setForm((current) => ({ ...current, accepts_financing: event.target.checked }))} type="checkbox" />Aceita financiamento</label>
                  <label><input checked={form.accepts_exchange} onChange={(event) => setForm((current) => ({ ...current, accepts_exchange: event.target.checked }))} type="checkbox" />Aceita permuta</label>
                </> : null}
                {form.purpose !== "buy" ? <label className="form-span-2">
                  Garantias aceitas na locação
                  <input onChange={(event) => updateForm("rental_guarantees", event.target.value)} placeholder="Seguro-fiança, fiador, caução" value={form.rental_guarantees} />
                </label> : null}
                <label>
                  Telefone
                  <input
                    onChange={(event) => updateForm("advertiser_phone", event.target.value)}
                    value={form.advertiser_phone}
                  />
                </label>
                <label className="form-span-2">
                  Link de origem
                  <input
                    onChange={(event) => updateForm("source_url", event.target.value)}
                    placeholder="Opcional"
                    type="url"
                    value={form.source_url}
                  />
                </label>
              </div>

              <div className="property-photo-section">
                <div className="section-inline-header">
                  <div>
                    <strong>Fotos do imóvel</strong>
                    <span>Adicione imagens para compor a vitrine e os atendimentos.</span>
                  </div>
                  <label className="button-outline photo-upload-button">
                    <ImagePlus size={15} />
                    Adicionar fotos
                    <input accept="image/*" multiple onChange={handlePhotoUpload} type="file" />
                  </label>
                </div>

                {photos.length > 0 ? (
                  <div className="photo-preview-grid">
                    {photos.map((photo) => (
                      <div className="photo-preview-card" key={photo.id}>
                        <img alt={photo.file.name} src={photo.previewUrl} />
                        <button aria-label="Remover foto" onClick={() => removePhoto(photo.id)} type="button">
                          <X size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="photo-empty-state">Nenhuma foto adicionada.</div>
                )}
              </div>

              <fieldset className="checkbox-group form-span-2 image-ai-options">
                <legend>Otimização de imagens com IA</legend>
                {imageOptimizationOptions.map((option) => (
                  <label key={option.id}>
                    <input
                      checked={imageOptimizations.includes(option.id)}
                      onChange={() => toggleImageOptimization(option.id)}
                      type="checkbox"
                    />
                    {option.label}
                  </label>
                ))}
                <label className="image-ai-note">
                  Pedido adicional
                  <textarea
                    onChange={(event) => setImageOptimizationNote(event.target.value)}
                    placeholder="Opcional. Ex: deixar o ambiente mais claro sem alterar a estrutura do imóvel."
                    rows={3}
                    value={imageOptimizationNote}
                  />
                </label>
              </fieldset>

              <div className="modal-actions">
                {formMessage ? <div className="error-box">{formMessage}</div> : null}
                <button className="button-outline" onClick={closeCreateModal} type="button">
                  Cancelar
                </button>
                <button disabled={saving} type="submit">
                  {saving ? "Salvando..." : "Salvar imóvel"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

    </section>
  );
}
