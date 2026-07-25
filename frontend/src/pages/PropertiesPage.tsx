import { ArrowDown, ArrowUp, ImagePlus, RefreshCw, Star, Trash2, Plus, X } from "lucide-react";
import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { request, requestBlob } from "../api/client";
import type { Property, PropertyImage } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { PropertyCard } from "../components/PropertyCard";
import {
  ACCEPTED_PROPERTY_IMAGE_TYPES,
  atomicImageOrderSwap,
  mergeSavedProperty,
  propertySaveFailureMessage,
  validateImageSelection,
} from "../lib/propertyMediaState";

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
  { id: "visual_organization", label: "Organizar visualmente sem remover elementos" },
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

function propertyToForm(property: Property): PropertyForm {
  const address = property.address ?? {};
  const details = property.details ?? {};
  const currency = (value: unknown) =>
    value === null || value === undefined || value === ""
      ? ""
      : brlInputFormatter.format(Number(value));
  const list = (value: unknown) => Array.isArray(value) ? value.join(", ") : "";
  return {
    ...initialPropertyForm,
    listing_code: property.listing_code ?? "",
    title: property.title,
    purpose: property.purpose ?? "buy",
    property_type: property.property_type ?? "apartamento",
    category: property.category ?? "residential",
    street: String(address.street ?? ""),
    number: String(address.number ?? ""),
    complement: String(address.complement ?? ""),
    state: String(address.state ?? "SP"),
    postal_code: String(address.postal_code ?? ""),
    city: property.city,
    neighborhood: property.neighborhood ?? "",
    sale_price: currency(property.sale_price),
    rent_price: currency(property.rent_price),
    condo_fee: currency(details.condo_fee),
    property_tax: currency(details.property_tax),
    bedrooms: property.bedrooms?.toString() ?? "",
    suites: property.suites?.toString() ?? "",
    bathrooms: property.bathrooms?.toString() ?? "",
    parking_spaces: property.parking_spaces?.toString() ?? "",
    area: property.area?.toString() ?? "",
    land_area: property.land_area?.toString() ?? "",
    description: property.description ?? "",
    rooms: list(details.rooms),
    amenities: list(details.amenities),
    pet_friendly: Boolean(details.pet_friendly),
    furnished: Boolean(details.furnished),
    accepts_financing: Boolean(details.accepts_financing),
    accepts_exchange: Boolean(details.accepts_exchange),
    rental_guarantees: list(details.rental_guarantees),
    advertiser_name: property.advertiser_name ?? "",
    advertiser_phone: property.advertiser_phone ?? "",
    source_url: property.source_url ?? "",
  };
}

export function PropertiesPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<Property[]>([]);
  const [selected, setSelected] = useState<Property | null>(null);
  const [linkedImages, setLinkedImages] = useState<PropertyImage[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<string, string>>({});
  const objectUrls = useRef<Record<string, string>>({});
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [imageBusy, setImageBusy] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [form, setForm] = useState<PropertyForm>(initialPropertyForm);
  const [photos, setPhotos] = useState<PropertyPhoto[]>([]);
  const [imageOptimizations, setImageOptimizations] = useState<string[]>([]);
  const [imageOptimizationNote, setImageOptimizationNote] = useState("");
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    setListLoading(true);
    void request<Property[]>("/properties", {}, token)
      .then((properties) => {
        if (!active) return [];
        setItems(properties);
        setListError(null);
        return Promise.all(properties.map(async (property) => {
          try {
            const images = await request<PropertyImage[]>(`/properties/${property.id}/images`, {}, token);
            const primary = images.find((image) => image.is_primary) ?? images[0];
            if (!primary) return null;
            const blob = await requestBlob(primary.display_url, token);
            return [property.id, URL.createObjectURL(blob)] as const;
          } catch {
            return null;
          }
        }));
      })
      .then((entries) => {
        const next = Object.fromEntries(entries.filter(Boolean) as Array<readonly [string, string]>);
        if (!active) {
          Object.values(next).forEach(URL.revokeObjectURL);
          return;
        }
        replaceObjectUrls(next, (key) => !key.includes(":"));
      })
      .catch((error) => {
        if (active) setListError(error instanceof Error ? error.message : "Falha ao carregar imóveis.");
      })
      .finally(() => {
        if (active) setListLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => () => {
    Object.values(objectUrls.current).forEach(URL.revokeObjectURL);
    objectUrls.current = {};
  }, []);

  function replaceObjectUrls(
    entries: Record<string, string>,
    shouldReplace: (key: string) => boolean,
  ) {
    const current = objectUrls.current;
    Object.entries(current).forEach(([key, url]) => {
      if (shouldReplace(key) && entries[key] !== url) URL.revokeObjectURL(url);
    });
    const kept = Object.fromEntries(
      Object.entries(current).filter(([key]) => !shouldReplace(key)),
    );
    const next = { ...kept, ...entries };
    objectUrls.current = next;
    setImageUrls(next);
  }

  function removeObjectUrls(shouldRemove: (key: string) => boolean) {
    replaceObjectUrls({}, shouldRemove);
  }

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
    setSelected(null);
    removeObjectUrls((key) => key.startsWith("detail:") || key.startsWith("original:"));
    setLinkedImages([]);
    setIsCreateModalOpen(false);
  }

  async function openProperty(property: Property) {
    setSelected(property);
    setForm(propertyToForm(property));
    setPhotos([]);
    setFormMessage(null);
    setIsCreateModalOpen(true);
    await loadLinkedImages(property.id);
  }

  async function loadLinkedImages(propertyId: string) {
    try {
      const images = await request<PropertyImage[]>(`/properties/${propertyId}/images`, {}, token);
      const urls = await Promise.all(images.flatMap((image) => [
        requestBlob(image.display_url, token).then((blob) => [`detail:${image.id}`, URL.createObjectURL(blob)] as const),
        requestBlob(image.original_url, token).then((blob) => [`original:${image.id}`, URL.createObjectURL(blob)] as const),
      ]));
      replaceObjectUrls(
        Object.fromEntries(urls),
        (key) => key.startsWith("detail:") || key.startsWith("original:"),
      );
      setLinkedImages(images);
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "Falha ao carregar imagens.");
    }
  }

  async function refreshCover(propertyId: string) {
    try {
      const images = await request<PropertyImage[]>(`/properties/${propertyId}/images`, {}, token);
      await refreshCoverFromImages(propertyId, images);
    } catch {
      removeObjectUrls((key) => key === propertyId);
    }
  }

  async function refreshCoverFromImages(
    propertyId: string,
    images: PropertyImage[],
  ) {
    const primary = images.find((image) => image.is_primary) ?? images[0];
    if (!primary) {
      removeObjectUrls((key) => key === propertyId);
      return;
    }
    const blob = await requestBlob(primary.display_url, token);
    replaceObjectUrls(
      { [propertyId]: URL.createObjectURL(blob) },
      (key) => key === propertyId,
    );
  }

  function handlePhotoUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);

    if (!files.length) {
      return;
    }

    const selectionError = validateImageSelection(
      photos.length + linkedImages.length,
      files,
    );
    if (selectionError) {
      setFormMessage(selectionError);
      event.target.value = "";
      return;
    }
    setFormMessage(null);
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

  function propertyPayload(status = selected?.status ?? "active") {
    return {
      status,
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
        street: form.street.trim(), number: form.number.trim() || null,
        complement: form.complement.trim() || null, neighborhood: form.neighborhood.trim(),
        city: form.city.trim(), state: form.state.trim().toUpperCase(),
        postal_code: form.postal_code.trim() || null,
      },
      details: {
        condo_fee: parseCurrencyInput(form.condo_fee) || null,
        property_tax: parseCurrencyInput(form.property_tax) || null,
        pet_friendly: form.pet_friendly, furnished: form.furnished,
        accepts_financing: form.accepts_financing, accepts_exchange: form.accepts_exchange,
        rental_guarantees: splitList(form.rental_guarantees),
        rooms: splitList(form.rooms), amenities: splitList(form.amenities),
      },
      owner_name: form.advertiser_name.trim() || null,
      owner_phone: form.advertiser_phone.trim() || null,
      source_url: form.source_url.trim() || null,
    };
  }

  async function handleCreateProperty(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormMessage(null);
    let persistedProperty: Property | null = null;
    let originalsPersisted = false;
    const wasEditing = Boolean(selected);

    try {
      const property = await request<Property>(selected ? `/properties/${selected.id}` : "/properties", {
        method: selected ? "PUT" : "POST",
        body: JSON.stringify(propertyPayload()),
      }, token);
      persistedProperty = property;
      setSelected(property);
      setItems((current) => mergeSavedProperty(current, property, wasEditing));
      if (photos.length) {
        const body = new FormData();
        photos.forEach((photo) => body.append("files", photo.file));
        const uploaded = await request<PropertyImage[]>(`/properties/${property.id}/images`, { method: "POST", body }, token);
        originalsPersisted = true;
        photos.forEach((photo) => URL.revokeObjectURL(photo.previewUrl));
        setPhotos([]);
        await loadLinkedImages(property.id);
        await refreshCover(property.id);
        if (imageOptimizations.length || imageOptimizationNote.trim()) {
          for (const image of uploaded) {
            await request<PropertyImage>(`/properties/${property.id}/images/${image.id}/reprocess`, {
              method: "POST",
              body: JSON.stringify({ optimizations: imageOptimizations, note: imageOptimizationNote.trim() || null }),
            }, token);
            await loadLinkedImages(property.id);
            await refreshCover(property.id);
          }
        }
      }
      await refreshCover(property.id);
    } catch (error) {
      const reason = error instanceof Error ? error.message : "Erro inesperado.";
      setFormMessage(
        propertySaveFailureMessage(
          reason,
          Boolean(persistedProperty),
          originalsPersisted,
          wasEditing,
        ),
      );
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

  async function changeStatus() {
    if (!selected) return;
    if (!window.confirm(selected.status === "inactive" ? "Reativar este imóvel?" : "Inativar este imóvel? Ele deixará de ser oferecido nos atendimentos.")) return;
    setSaving(true);
    try {
      const updated = await request<Property>(`/properties/${selected.id}/status`, {
        method: "PATCH", body: JSON.stringify({ status: selected.status === "inactive" ? "active" : "inactive" }),
      }, token);
      setSelected(updated);
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
      setFormMessage(updated.status === "inactive" ? "Imóvel inativado." : "Imóvel reativado.");
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "Falha ao alterar status.");
    } finally { setSaving(false); }
  }

  async function deleteSelected() {
    if (!selected || selected.status !== "inactive" || !window.confirm("Excluir este imóvel e todas as imagens definitivamente?")) return;
    setSaving(true);
    try {
      await request<void>(`/properties/${selected.id}`, { method: "DELETE" }, token);
      setItems((current) => current.filter((item) => item.id !== selected.id));
      removeObjectUrls((key) => key === selected.id);
      closeCreateModal();
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "Falha ao excluir imóvel.");
      setSaving(false);
    }
  }

  async function updateImage(image: PropertyImage, payload: { is_primary?: boolean; sort_order?: number }) {
    if (!selected) return;
    setImageBusy(image.id);
    try {
      await request<PropertyImage>(`/properties/${selected.id}/images/${image.id}`, {
        method: "PATCH", body: JSON.stringify(payload),
      }, token);
      await loadLinkedImages(selected.id);
      await refreshCover(selected.id);
    } catch (error) { setFormMessage(error instanceof Error ? error.message : "Falha ao atualizar imagem."); }
    finally { setImageBusy(null); }
  }

  async function moveImage(index: number, direction: -1 | 1) {
    if (!selected) return;
    const atomicOrder = atomicImageOrderSwap(linkedImages, index, direction);
    if (!atomicOrder) return;
    setImageBusy(linkedImages[index].id);
    try {
      const ordered = await request<PropertyImage[]>(`/properties/${selected.id}/images/order`, {
        method: "PUT",
        body: JSON.stringify({ images: atomicOrder }),
      }, token);
      setLinkedImages(ordered);
    } catch (error) { setFormMessage(error instanceof Error ? error.message : "Falha ao reordenar imagem."); }
    finally { setImageBusy(null); }
  }

  async function removeLinkedImage(image: PropertyImage) {
    if (!selected || !window.confirm("Remover esta imagem?")) return;
    setImageBusy(image.id);
    try {
      const remaining = await request<PropertyImage[]>(`/properties/${selected.id}/images/${image.id}`, { method: "DELETE" }, token);
      removeObjectUrls(
        (key) => key === `detail:${image.id}` || key === `original:${image.id}`,
      );
      setLinkedImages(remaining);
      await refreshCoverFromImages(selected.id, remaining);
    } catch (error) { setFormMessage(error instanceof Error ? error.message : "Falha ao remover imagem."); }
    finally { setImageBusy(null); }
  }

  async function reprocessImage(image: PropertyImage) {
    if (!selected) return;
    if (!window.confirm("Reprocessar a imagem original com IA? Esta operação pode consumir créditos.")) return;
    setImageBusy(image.id);
    try {
      await request<PropertyImage>(`/properties/${selected.id}/images/${image.id}/reprocess`, {
        method: "POST", body: JSON.stringify({ optimizations: imageOptimizations, note: imageOptimizationNote.trim() || null }),
      }, token);
      await loadLinkedImages(selected.id);
      await refreshCover(selected.id);
    } catch (error) { setFormMessage(error instanceof Error ? error.message : "Falha ao reprocessar imagem."); }
    finally { setImageBusy(null); }
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

      {listError ? <div className="error-box">{listError}</div> : null}
      {listLoading ? (
        <div className="empty-state large">Carregando imóveis...</div>
      ) : items.length > 0 ? (
        <div className="property-grid">
          {items.map((property) => (
            <PropertyCard
              imageUrl={imageUrls[property.id]}
              key={property.id}
              onClick={() => void openProperty(property)}
              property={property}
            />
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
                <h2>{selected ? "Detalhes do imóvel" : "Cadastrar imóvel"}</h2>
                <p>{selected ? "Edite o cadastro e gerencie as imagens vinculadas." : "O imóvel será cadastrado antes do envio das imagens."}</p>
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
                    <span>JPEG, PNG ou WebP · até 10 MB cada · máximo de 12 imagens por imóvel.</span>
                  </div>
                  <label className="button-outline photo-upload-button">
                    <ImagePlus size={15} />
                    Adicionar fotos
                    <input accept={ACCEPTED_PROPERTY_IMAGE_TYPES.join(",")} multiple onChange={handlePhotoUpload} type="file" />
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

              {selected ? (
                <div className="property-photo-section">
                  <div className="section-inline-header">
                    <div>
                      <strong>Imagens vinculadas</strong>
                      <span>Original preservado; a versão tratada é usada na exibição.</span>
                    </div>
                  </div>
                  {linkedImages.length ? (
                    <div className="linked-image-grid">
                      {linkedImages.map((image, index) => (
                        <article className="linked-image-card" key={image.id}>
                          <img alt={image.original_name} src={imageUrls[`detail:${image.id}`]} />
                          <div>
                            <strong>{image.original_name}</strong>
                            <span>{image.status}{image.is_primary ? " · principal" : ""}</span>
                            {image.error ? <small>{image.error}</small> : null}
                          </div>
                          <div className="linked-image-actions">
                            <button aria-label="Definir como principal" disabled={imageBusy === image.id || image.is_primary} onClick={() => void updateImage(image, { is_primary: true })} type="button"><Star size={14} /></button>
                            <button aria-label="Mover para cima" disabled={imageBusy === image.id || index === 0} onClick={() => void moveImage(index, -1)} type="button"><ArrowUp size={14} /></button>
                            <button aria-label="Mover para baixo" disabled={imageBusy === image.id || index === linkedImages.length - 1} onClick={() => void moveImage(index, 1)} type="button"><ArrowDown size={14} /></button>
                            <button aria-label="Reprocessar original" disabled={imageBusy === image.id} onClick={() => void reprocessImage(image)} type="button"><RefreshCw size={14} /></button>
                            <a className="button-outline" href={imageUrls[`original:${image.id}`]} target="_blank" rel="noreferrer">Original</a>
                            {image.derived_size ? <a className="button-outline" href={imageUrls[`detail:${image.id}`]} target="_blank" rel="noreferrer">Tratada</a> : null}
                            <button aria-label="Remover imagem" className="button-danger" disabled={imageBusy === image.id} onClick={() => void removeLinkedImage(image)} type="button"><Trash2 size={14} /></button>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : <div className="photo-empty-state">Nenhuma imagem vinculada.</div>}
                </div>
              ) : null}

              <fieldset className="checkbox-group form-span-2 image-ai-options">
                <legend>Otimização de imagens com IA</legend>
                <p className="field-help">
                  O tratamento preserva arquitetura, móveis, objetos e proporções. Ele não adiciona,
                  remove nem inventa elementos; aplica apenas ajustes visuais conservadores.
                </p>
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
                {selected ? (
                  <>
                    <button className="button-outline" disabled={saving} onClick={() => void changeStatus()} type="button">
                      {selected.status === "inactive" ? "Reativar" : "Inativar"}
                    </button>
                    {selected.status === "inactive" ? (
                      <button className="button-danger" disabled={saving} onClick={() => void deleteSelected()} type="button">
                        Excluir definitivamente
                      </button>
                    ) : null}
                  </>
                ) : null}
                <button className="button-outline" onClick={closeCreateModal} type="button">
                  Cancelar
                </button>
                <button disabled={saving} type="submit">
                  {saving ? "Salvando..." : selected ? "Salvar alterações" : "Salvar imóvel"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

    </section>
  );
}
