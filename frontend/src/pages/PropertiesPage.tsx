import { ArrowLeft, ChevronLeft, ChevronRight, Download, Film, ImagePlus, LoaderCircle, Play, RotateCcw, Sparkles, Trash2, Plus, X } from "lucide-react";
import { type DragEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { request, requestBlob, requestBlobWithProgress, uploadFormDataWithProgress } from "../api/client";
import type { Property, PropertyImage } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { PropertyCard } from "../components/PropertyCard";
import {
  ACCEPTED_PROPERTY_MEDIA_TYPES,
  atomicImageOrderSwap,
  isPropertyImage,
  mergeSavedProperty,
  propertySaveFailureMessage,
  reconcileImageOptimizationSelection,
  toggleImageOptimizationSelection,
  validateMediaSelection,
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

type PendingPropertyMedia = {
  id: string;
  file: File;
  previewUrl: string;
  status: "pending" | "uploading" | "ready" | "failed";
  progress: number;
  error: string | null;
  stagingId: string | null;
};

type StagedPropertyMedia = {
  id: string;
  original_name: string;
  content_type: string;
  size: number;
};

type ImageVersion = "original" | "optimized";

type ImageLightbox = {
  name: string;
  url: string;
  version: ImageVersion;
};

const imageOptimizationOptions = [
  { id: "lighting", label: "Melhorar iluminação" },
  { id: "straighten", label: "Corrigir enquadramento" },
  { id: "visual_organization", label: "Organizar visualmente sem remover elementos" },
  { id: "walls", label: "Suavizar marcas em paredes" },
  { id: "windows", label: "Realçar vista e janelas" },
  { id: "sharpen", label: "Aumentar nitidez" },
  { id: "remove_furniture", label: "Remover mobília" },
  { id: "add_furniture", label: "Adicionar mobília" },
];

const mutuallyExclusiveFurnitureOptions: Record<string, string> = {
  remove_furniture: "add_furniture",
  add_furniture: "remove_furniture",
};

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
  const [imageVersions, setImageVersions] = useState<Record<string, ImageVersion>>({});
  const [imageLightbox, setImageLightbox] = useState<ImageLightbox | null>(null);
  const objectUrls = useRef<Record<string, string>>({});
  const mediaLoadVersion = useRef(0);
  const mediaInputRef = useRef<HTMLInputElement>(null);
  const [mediaLoading, setMediaLoading] = useState(false);
  const [mediaUploading, setMediaUploading] = useState(false);
  const [mediaPreviewErrors, setMediaPreviewErrors] = useState<Record<string, string>>({});
  const [videoLoadProgress, setVideoLoadProgress] = useState<Record<string, number>>({});
  const [videoLoadErrors, setVideoLoadErrors] = useState<Record<string, string>>({});
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [imageBusy, setImageBusy] = useState<string | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [isAiModalOpen, setIsAiModalOpen] = useState(false);
  const [isMediaModalOpen, setIsMediaModalOpen] = useState(false);
  const [isMediaDropActive, setIsMediaDropActive] = useState(false);
  const [form, setForm] = useState<PropertyForm>(initialPropertyForm);
  const [pendingMedia, setPendingMedia] = useState<PendingPropertyMedia[]>([]);
  const [imageOptimizations, setImageOptimizations] = useState<string[]>([]);
  const [imageOptimizationNote, setImageOptimizationNote] = useState("");
  const [selectedImageIds, setSelectedImageIds] = useState<string[]>([]);
  const [optimizationProgress, setOptimizationProgress] = useState<string | null>(null);
  const [aiMessage, setAiMessage] = useState<string | null>(null);
  const [aiMessageKind, setAiMessageKind] = useState<"success" | "error">("success");
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [formMessageKind, setFormMessageKind] = useState<"success" | "error">("success");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    setListLoading(true);
    void request<Property[]>("/properties", {}, token)
      .then((properties) => {
        if (!active) return [];
        const internalProperties = properties.filter((property) => property.source === "manual");
        setItems(internalProperties);
        setListError(null);
        return Promise.all(internalProperties.map(async (property) => {
          try {
            const images = await request<PropertyImage[]>(`/properties/${property.id}/images`, {}, token);
            const propertyImages = images.filter(isPropertyImage);
            const primary = propertyImages.find((image) => image.is_primary) ?? propertyImages[0];
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

  async function discardStagedMedia(mediaItems: PendingPropertyMedia[]) {
    await Promise.all(mediaItems
      .filter((media) => media.stagingId)
      .map((media) => request<void>(`/properties/media/staging/${media.stagingId}`, { method: "DELETE" }, token).catch(() => undefined)));
  }

  async function closePropertyDetail() {
    mediaLoadVersion.current += 1;
    await discardStagedMedia(pendingMedia);
    pendingMedia.forEach((media) => URL.revokeObjectURL(media.previewUrl));
    setPendingMedia([]);
    setImageOptimizations([]);
    setImageOptimizationNote("");
    setSelectedImageIds([]);
    setOptimizationProgress(null);
    setAiMessage(null);
    setAiMessageKind("success");
    setIsAiModalOpen(false);
    setIsMediaModalOpen(false);
    setImageLightbox(null);
    setImageVersions({});
    setForm(initialPropertyForm);
    setFormMessage(null);
    setFormMessageKind("success");
    setSelected(null);
    removeObjectUrls((key) => key.startsWith("detail:") || key.startsWith("original:"));
    setLinkedImages([]);
    setMediaLoading(false);
    setMediaPreviewErrors({});
    setVideoLoadProgress({});
    setVideoLoadErrors({});
    setIsDetailOpen(false);
  }

  function openCreateProperty() {
    setSelected(null);
    setForm(initialPropertyForm);
    setPendingMedia([]);
    setLinkedImages([]);
    setMediaLoading(false);
    setMediaPreviewErrors({});
    setVideoLoadProgress({});
    setVideoLoadErrors({});
    setImageOptimizations([]);
    setImageOptimizationNote("");
    setSelectedImageIds([]);
    setOptimizationProgress(null);
    setAiMessage(null);
    setAiMessageKind("success");
    setFormMessage(null);
    setFormMessageKind("success");
    setIsAiModalOpen(false);
    setIsMediaModalOpen(false);
    setImageLightbox(null);
    setImageVersions({});
    setIsDetailOpen(true);
  }

  async function openProperty(property: Property) {
    setSelected(property);
    setForm(propertyToForm(property));
    setPendingMedia([]);
    setMediaLoading(true);
    setMediaPreviewErrors({});
    setVideoLoadProgress({});
    setVideoLoadErrors({});
    setImageOptimizations([]);
    setImageOptimizationNote("");
    setSelectedImageIds([]);
    setOptimizationProgress(null);
    setAiMessage(null);
    setAiMessageKind("success");
    setFormMessage(null);
    setFormMessageKind("success");
    setIsAiModalOpen(false);
    setIsMediaModalOpen(false);
    setImageLightbox(null);
    setImageVersions({});
    setIsDetailOpen(true);
    await loadLinkedImages(property.id);
  }

  async function loadLinkedImages(propertyId: string) {
    const loadVersion = ++mediaLoadVersion.current;
    setMediaLoading(true);
    try {
      const images = await request<PropertyImage[]>(`/properties/${propertyId}/images`, {}, token);
      if (loadVersion !== mediaLoadVersion.current) return;
      setLinkedImages(images);
      setImageVersions((current) => Object.fromEntries(
        images.filter(isPropertyImage).map((image) => [
          image.id,
          current[image.id] ?? (image.derived_size ? "optimized" : "original"),
        ]),
      ));
      setSelectedImageIds((current) =>
        reconcileImageOptimizationSelection(current, images.filter(isPropertyImage)),
      );
      setMediaLoading(false);
      images.filter(isPropertyImage).forEach((image) => {
        void loadImagePreview(image, loadVersion);
      });
    } catch (error) {
      if (loadVersion !== mediaLoadVersion.current) return;
      setFormMessage(error instanceof Error ? error.message : "Falha ao carregar mídias.");
      setFormMessageKind("error");
      setMediaLoading(false);
    }
  }

  async function loadImagePreview(image: PropertyImage, loadVersion: number) {
    try {
      const [displayBlob, originalBlob] = await Promise.all([
        requestBlob(image.display_url, token),
        requestBlob(image.original_url, token),
      ]);
      if (loadVersion !== mediaLoadVersion.current) return;
      replaceObjectUrls(
        {
          [`detail:${image.id}`]: URL.createObjectURL(displayBlob),
          [`original:${image.id}`]: URL.createObjectURL(originalBlob),
        },
        (key) => key === `detail:${image.id}` || key === `original:${image.id}`,
      );
      setMediaPreviewErrors((current) => {
        const next = { ...current };
        delete next[image.id];
        return next;
      });
    } catch (error) {
      if (loadVersion !== mediaLoadVersion.current) return;
      setMediaPreviewErrors((current) => ({
        ...current,
        [image.id]: error instanceof Error ? error.message : "Falha ao carregar a foto.",
      }));
    }
  }

  async function loadVideoContent(media: PropertyImage) {
    if (imageUrls[`detail:${media.id}`]) return;
    setVideoLoadErrors((current) => {
      const next = { ...current };
      delete next[media.id];
      return next;
    });
    setVideoLoadProgress((current) => ({ ...current, [media.id]: 0 }));
    try {
      const blob = await requestBlobWithProgress(
        media.display_url,
        token,
        (progress) => setVideoLoadProgress((current) => ({ ...current, [media.id]: progress })),
        media.original_size,
      );
      replaceObjectUrls(
        { [`detail:${media.id}`]: URL.createObjectURL(blob) },
        (key) => key === `detail:${media.id}`,
      );
    } catch (error) {
      setVideoLoadErrors((current) => ({
        ...current,
        [media.id]: error instanceof Error ? error.message : "Falha ao carregar o vídeo.",
      }));
    } finally {
      setVideoLoadProgress((current) => {
        const next = { ...current };
        delete next[media.id];
        return next;
      });
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
    const availableImages = images.filter(isPropertyImage);
    const primary = availableImages.find((image) => image.is_primary) ?? availableImages[0];
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

  function addMediaFiles(files: File[]) {
    if (!files.length) return;
    const selectionError = validateMediaSelection(
      pendingMedia.length + linkedImages.length,
      files,
    );
    if (selectionError) {
      setFormMessage(selectionError);
      setFormMessageKind("error");
      return;
    }
    setFormMessage(null);
    const mediaItems: PendingPropertyMedia[] = files.map((file) => ({
        id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`,
        file,
        previewUrl: URL.createObjectURL(file),
        status: "pending" as const,
        progress: 0,
        error: null,
        stagingId: null,
      }));
    setPendingMedia((current) => [...current, ...mediaItems]);
    void stagePendingMedia(mediaItems);
  }

  async function removePendingMedia(mediaId: string) {
    const media = pendingMedia.find((item) => item.id === mediaId);
    if (!media || media.status === "uploading") return;
    if (media.stagingId) {
      try {
        await request<void>(`/properties/media/staging/${media.stagingId}`, { method: "DELETE" }, token);
      } catch (error) {
        updatePendingMedia(media.id, {
          error: error instanceof Error ? error.message : "Falha ao descartar a mídia.",
        });
        return;
      }
    }
    setPendingMedia((current) => {
      URL.revokeObjectURL(media.previewUrl);
      return current.filter((item) => item.id !== mediaId);
    });
  }

  function updatePendingMedia(
    mediaId: string,
    patch: Partial<Pick<PendingPropertyMedia, "status" | "progress" | "error" | "stagingId">>,
  ) {
    setPendingMedia((current) => current.map((media) =>
      media.id === mediaId ? { ...media, ...patch } : media,
    ));
  }

  async function stagePendingMedia(
    mediaItems: PendingPropertyMedia[],
  ) {
    let uploadedCount = 0;
    let failedCount = 0;
    setMediaUploading(true);
    try {
      for (const media of mediaItems) {
        updatePendingMedia(media.id, { status: "uploading", progress: 0, error: null });
        const body = new FormData();
        body.append("file", media.file);
        try {
          const staged = await uploadFormDataWithProgress<StagedPropertyMedia>(
            "/properties/media/staging",
            body,
            token,
            {
              onProgress: (progress) => updatePendingMedia(media.id, { progress }),
              timeoutMs: media.file.type.startsWith("video/") ? 10 * 60_000 : 3 * 60_000,
            },
          );
          uploadedCount += 1;
          updatePendingMedia(media.id, {
            status: "ready",
            progress: 100,
            stagingId: staged.id,
          });
        } catch (error) {
          failedCount += 1;
          updatePendingMedia(media.id, {
            status: "failed",
            progress: 0,
            error: error instanceof Error ? error.message : "Falha ao enviar a mídia.",
          });
        }
      }
    } finally {
      setMediaUploading(false);
    }
    return { uploadedCount, failedCount };
  }

  async function retryMediaUpload(media: PendingPropertyMedia) {
    if (mediaUploading) return;
    const { uploadedCount, failedCount } = await stagePendingMedia([media]);
    setFormMessage(
      failedCount
        ? "O reenvio falhou. Confira a mensagem exibida na mídia e tente novamente."
        : `${uploadedCount === 1 ? "Mídia preparada" : "Mídias preparadas"} com sucesso.`,
    );
    setFormMessageKind(failedCount ? "error" : "success");
  }

  function handleMediaDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsMediaDropActive(false);
    if (mediaUploading) return;
    addMediaFiles(Array.from(event.dataTransfer.files));
  }

  function toggleImageOptimization(optionId: string) {
    setImageOptimizations((current) => {
      if (current.includes(optionId)) return current.filter((item) => item !== optionId);
      const incompatibleOption = mutuallyExclusiveFurnitureOptions[optionId];
      return [...current.filter((item) => item !== incompatibleOption), optionId];
    });
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
    const wasEditing = Boolean(selected);

    try {
      const property = await request<Property>(selected ? `/properties/${selected.id}` : "/properties", {
        method: selected ? "PUT" : "POST",
        body: JSON.stringify(propertyPayload()),
      }, token);
      persistedProperty = property;
      setSelected(property);
      setItems((current) => mergeSavedProperty(current, property, wasEditing));
    } catch (error) {
      const reason = error instanceof Error ? error.message : "Erro inesperado.";
      setFormMessage(
        propertySaveFailureMessage(
          reason,
          Boolean(persistedProperty),
          false,
          wasEditing,
        ),
      );
      setFormMessageKind("error");
      setSaving(false);
      return;
    }
    if (persistedProperty) setForm(propertyToForm(persistedProperty));
    setSaving(false);
    const preparedMedia = pendingMedia.filter((media) => media.status === "ready" && media.stagingId);
    const failedMediaCount = pendingMedia.filter((media) => media.status === "failed").length;
    if (persistedProperty && preparedMedia.length) {
      setSaving(true);
      try {
        const uploaded = await request<PropertyImage[]>(`/properties/${persistedProperty.id}/images/commit`, {
          method: "POST",
          body: JSON.stringify({ staging_ids: preparedMedia.map((media) => media.stagingId) }),
        }, token);
        const previewUrls: Record<string, string> = {};
        uploaded.forEach((media, index) => {
          const prepared = preparedMedia[index];
          previewUrls[`detail:${media.id}`] = prepared.previewUrl;
          if (isPropertyImage(media)) previewUrls[`original:${media.id}`] = prepared.previewUrl;
        });
        replaceObjectUrls(previewUrls, (key) => uploaded.some((media) => key.endsWith(`:${media.id}`)));
        setPendingMedia((current) => current.filter((media) => !preparedMedia.some((prepared) => prepared.id === media.id)));
        setLinkedImages((current) => [...current, ...uploaded]);
        await refreshCover(persistedProperty.id);
        const uploadedCount = uploaded.length;
        setFormMessage(
          failedMediaCount
            ? `${uploadedCount} ${uploadedCount === 1 ? "mídia salva" : "mídias salvas"}; ${failedMediaCount} ${failedMediaCount === 1 ? "falhou" : "falharam"} durante a preparação.`
            : `${uploadedCount} ${uploadedCount === 1 ? "mídia salva" : "mídias salvas"} sem novo carregamento.`,
        );
        setFormMessageKind(failedMediaCount ? "error" : "success");
      } catch (error) {
        setFormMessage(error instanceof Error ? error.message : "Falha ao vincular as mídias preparadas.");
        setFormMessageKind("error");
      } finally {
        setSaving(false);
      }
      return;
    }
    await refreshCover(persistedProperty!.id);
    setFormMessage(
      failedMediaCount
        ? `Os dados foram salvos, mas ${failedMediaCount} ${failedMediaCount === 1 ? "mídia falhou" : "mídias falharam"} durante a preparação. Tente novamente.`
        : wasEditing ? "Alterações salvas." : "Imóvel salvo. Você pode adicionar fotos e vídeos agora ou voltar para a carteira.",
    );
    setFormMessageKind(failedMediaCount ? "error" : "success");
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
      setFormMessageKind("success");
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "Falha ao alterar status.");
      setFormMessageKind("error");
    } finally { setSaving(false); }
  }

  async function deleteSelected() {
    if (!selected || selected.status !== "inactive" || !window.confirm("Excluir este imóvel e todas as mídias definitivamente?")) return;
    setSaving(true);
    try {
      await request<void>(`/properties/${selected.id}`, { method: "DELETE" }, token);
      setItems((current) => current.filter((item) => item.id !== selected.id));
      removeObjectUrls((key) => key === selected.id);
      closePropertyDetail();
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "Falha ao excluir imóvel.");
      setFormMessageKind("error");
      setSaving(false);
    }
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
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "Falha ao reordenar mídia.");
      setFormMessageKind("error");
    }
    finally { setImageBusy(null); }
  }

  async function removeLinkedImage(image: PropertyImage) {
    const mediaLabel = isPropertyImage(image) ? "imagem" : "vídeo";
    if (!selected || !window.confirm(`Remover ${mediaLabel === "imagem" ? "esta" : "este"} ${mediaLabel}?`)) return;
    setImageBusy(image.id);
    try {
      const remaining = await request<PropertyImage[]>(`/properties/${selected.id}/images/${image.id}`, { method: "DELETE" }, token);
      removeObjectUrls(
        (key) => key === `detail:${image.id}` || key === `original:${image.id}`,
      );
      setLinkedImages(remaining);
      setSelectedImageIds((current) =>
        reconcileImageOptimizationSelection(current, remaining.filter(isPropertyImage)),
      );
      await refreshCoverFromImages(selected.id, remaining);
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "Falha ao remover mídia.");
      setFormMessageKind("error");
    }
    finally { setImageBusy(null); }
  }

  async function optimizeImages(images: PropertyImage[]) {
    const optimizableImages = images.filter(isPropertyImage);
    if (!selected || !optimizableImages.length) return;
    images = optimizableImages;
    const count = images.length;
    if (!window.confirm(
      `Otimizar ${count} ${count === 1 ? "imagem" : "imagens"} com IA? Cada imagem concluída usa uma unidade da franquia de otimização.`,
    )) return;
    setImageBusy(count === 1 ? images[0].id : "batch");
    setOptimizationProgress(`Otimizando 1 de ${count}...`);
    let completed = 0;
    try {
      for (const image of images) {
        setOptimizationProgress(`Otimizando ${completed + 1} de ${count}...`);
        await request<PropertyImage>(`/properties/${selected.id}/images/${image.id}/reprocess`, {
          method: "POST",
          body: JSON.stringify({
            optimizations: imageOptimizations,
            note: imageOptimizationNote.trim() || null,
          }),
        }, token);
        setImageVersions((current) => ({ ...current, [image.id]: "optimized" }));
        completed += 1;
      }
      await loadLinkedImages(selected.id);
      await refreshCover(selected.id);
      setSelectedImageIds((current) =>
        current.filter((id) => !images.some((image) => image.id === id)),
      );
      const successMessage = `${completed} ${completed === 1 ? "imagem otimizada" : "imagens otimizadas"} com IA. Os originais continuam preservados.`;
      setFormMessage(successMessage);
      setFormMessageKind("success");
      setAiMessage(successMessage);
      setAiMessageKind("success");
    } catch (error) {
      await loadLinkedImages(selected.id);
      await refreshCover(selected.id);
      const reason = error instanceof Error ? error.message : "Falha ao otimizar imagem.";
      const failureMessage = completed
        ? `${completed} de ${count} imagens foram otimizadas antes da falha: ${reason}`
        : reason;
      setFormMessage(failureMessage);
      setFormMessageKind("error");
      setAiMessage(failureMessage);
      setAiMessageKind("error");
    } finally {
      setOptimizationProgress(null);
      setImageBusy(null);
    }
  }

  function optimizeSelectedImages() {
    const selectedImages = linkedImages.filter((image) => selectedImageIds.includes(image.id));
    void optimizeImages(selectedImages);
  }

  const optimizableImages = linkedImages.filter(isPropertyImage);

  function imageVersionFor(media: PropertyImage): ImageVersion {
    return imageVersions[media.id] ?? (media.derived_size ? "optimized" : "original");
  }

  function imageUrlFor(media: PropertyImage, version = imageVersionFor(media)) {
    return imageUrls[`${version === "optimized" ? "detail" : "original"}:${media.id}`];
  }

  function selectImageVersion(media: PropertyImage, version: ImageVersion) {
    if (version === "optimized" && !media.derived_size) return;
    setImageVersions((current) => ({ ...current, [media.id]: version }));
  }

  function openImageLightbox(media: PropertyImage) {
    const version = imageVersionFor(media);
    const url = imageUrlFor(media, version);
    if (url) setImageLightbox({ name: media.original_name, url, version });
  }

  return (
    <section className="page-stack properties-page">
      {!isDetailOpen ? (
        <>
          <div className="property-toolbar">
            <h2>Carteira de imóveis</h2>
            <div className="toolbar-actions">
              <button className="button-outline" onClick={openCreateProperty} type="button">
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
        </>
      ) : (
        <div className="property-detail-view">
          <div className="property-detail-navigation">
            <button className="button-outline" disabled={saving || mediaUploading || Boolean(imageBusy)} onClick={() => void closePropertyDetail()} type="button">
              <ArrowLeft size={16} /> Voltar
            </button>
            <div>
              <span className="eyebrow">Carteira própria</span>
              <h2>{selected ? selected.title : "Cadastrar imóvel"}</h2>
              <p>{selected ? "Edite o cadastro e gerencie as mídias do imóvel." : "Preencha os dados e adicione as mídias do imóvel."}</p>
            </div>
          </div>

          <section className="property-detail-panel">
            <div className="property-detail-section-header">
              <div>
                <span className="eyebrow">Dados do imóvel</span>
                <h3>{selected ? "Detalhes do cadastro" : "Novo cadastro"}</h3>
              </div>
              {selected?.listing_code ? <span className="property-code-chip">Código {selected.listing_code}</span> : null}
            </div>

            <form onSubmit={handleCreateProperty}>
              <p className="required-fields-note"><span aria-hidden="true">*</span> Campo obrigatório</p>
              <div className="form-grid">
                <label className="form-span-2">
                  <span className="field-label">Título do imóvel <span aria-hidden="true" className="required-marker">*</span></span>
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
                  <span className="field-label">Finalidade <span aria-hidden="true" className="required-marker">*</span></span>
                  <select onChange={(event) => updateForm("purpose", event.target.value)} required value={form.purpose}>
                    <option value="buy">Venda</option>
                    <option value="rent">Locação</option>
                    <option value="both">Venda e locação</option>
                  </select>
                </label>
                <label>
                  <span className="field-label">Categoria <span aria-hidden="true" className="required-marker">*</span></span>
                  <select onChange={(event) => updateForm("category", event.target.value)} required value={form.category}>
                    <option value="residential">Residencial</option>
                    <option value="commercial">Comercial</option>
                    <option value="mixed">Residencial e comercial</option>
                  </select>
                </label>
                <label>
                  <span className="field-label">Tipo <span aria-hidden="true" className="required-marker">*</span></span>
                  <select
                    onChange={(event) => updateForm("property_type", event.target.value)}
                    required
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
                  <span className="field-label">Logradouro <span aria-hidden="true" className="required-marker">*</span></span>
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
                  <span className="field-label">Cidade <span aria-hidden="true" className="required-marker">*</span></span>
                  <input onChange={(event) => updateForm("city", event.target.value)} required value={form.city} />
                </label>
                <label>
                  <span className="field-label">Bairro <span aria-hidden="true" className="required-marker">*</span></span>
                  <input onChange={(event) => updateForm("neighborhood", event.target.value)} required value={form.neighborhood} />
                </label>
                <label>
                  <span className="field-label">UF <span aria-hidden="true" className="required-marker">*</span></span>
                  <input maxLength={2} onChange={(event) => updateForm("state", event.target.value)} required value={form.state} />
                </label>
                <label>
                  CEP
                  <input onChange={(event) => updateForm("postal_code", event.target.value)} value={form.postal_code} />
                </label>
                {form.purpose !== "rent" ? <label>
                  <span className="field-label">Valor de venda <span aria-hidden="true" className="required-marker">*</span></span>
                  <input
                    inputMode="numeric"
                    onChange={(event) => updateForm("sale_price", formatCurrencyInput(event.target.value))}
                    placeholder="R$ 850.000,00"
                    required
                    value={form.sale_price}
                  />
                </label> : null}
                {form.purpose !== "buy" ? <label>
                  <span className="field-label">Aluguel mensal <span aria-hidden="true" className="required-marker">*</span></span>
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
                <div className="form-span-2 property-checkbox-grid">
                  <label className="property-checkbox">
                    <input checked={form.pet_friendly} onChange={(event) => setForm((current) => ({ ...current, pet_friendly: event.target.checked }))} type="checkbox" />
                    <span>Aceita pet</span>
                  </label>
                  <label className="property-checkbox">
                    <input checked={form.furnished} onChange={(event) => setForm((current) => ({ ...current, furnished: event.target.checked }))} type="checkbox" />
                    <span>Mobiliado</span>
                  </label>
                  {form.purpose !== "rent" ? <>
                    <label className="property-checkbox"><input checked={form.accepts_financing} onChange={(event) => setForm((current) => ({ ...current, accepts_financing: event.target.checked }))} type="checkbox" /><span>Aceita financiamento</span></label>
                    <label className="property-checkbox"><input checked={form.accepts_exchange} onChange={(event) => setForm((current) => ({ ...current, accepts_exchange: event.target.checked }))} type="checkbox" /><span>Aceita permuta</span></label>
                  </> : null}
                </div>
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

              <section className="property-media-section">
                <div className="section-inline-header">
                  <div>
                    <strong>Mídias do imóvel</strong>
                    <span>Fotos de até 10 MB e vídeos MP4, MOV ou WebM de até 100 MB. Máximo de 12 mídias.</span>
                  </div>
                  <div className="property-media-header-actions">
                    {selected && linkedImages.some(isPropertyImage) ? (
                      <button
                        className="button-outline image-optimize-button"
                        disabled={saving || mediaUploading || Boolean(imageBusy)}
                        onClick={() => {
                          setSelectedImageIds([]);
                          setAiMessage(null);
                          setAiMessageKind("success");
                          setIsAiModalOpen(true);
                        }}
                        type="button"
                      >
                        <Sparkles size={15} /> Otimizar fotos com IA
                      </button>
                    ) : null}
                    <button
                      className="button-outline photo-upload-button"
                      disabled={saving || mediaUploading || Boolean(imageBusy)}
                      onClick={() => setIsMediaModalOpen(true)}
                      type="button"
                    >
                      <ImagePlus size={15} />
                      Adicionar mídias
                    </button>
                  </div>
                </div>

                {pendingMedia.length ? (
                  <div className="property-media-grid pending">
                    {pendingMedia.map((media) => {
                      const isImage = media.file.type.startsWith("image/");
                      return (
                        <article className="property-media-card pending" key={media.id}>
                          <div className="property-media-preview">
                            {isImage ? (
                              <img alt={media.file.name} src={media.previewUrl} />
                            ) : (
                              <video aria-label={media.file.name} muted preload="metadata" src={media.previewUrl} />
                            )}
                            <span>{isImage ? "Nova foto" : "Novo vídeo"}</span>
                          </div>
                          <div className="property-media-card-body">
                            <strong>{media.file.name}</strong>
                            <span>
                              {media.status === "uploading"
                                ? `Enviando ${media.progress}% · ${formatFileSize(media.file.size)}`
                                : media.status === "failed"
                                  ? "Falha no envio"
                                  : media.status === "ready"
                                    ? `Pronta para salvar · ${formatFileSize(media.file.size)}`
                                    : `Preparando · ${formatFileSize(media.file.size)}`}
                            </span>
                            {media.status === "uploading" ? (
                              <div aria-label={`Progresso do upload: ${media.progress}%`} className="media-progress" role="progressbar" aria-valuemax={100} aria-valuemin={0} aria-valuenow={media.progress}>
                                <span style={{ width: `${media.progress}%` }} />
                              </div>
                            ) : null}
                            {media.error ? <small className="media-error">{media.error}</small> : null}
                            <div className="property-media-card-actions">
                              {media.status === "failed" ? (
                                <button className="button-outline" disabled={mediaUploading} onClick={() => void retryMediaUpload(media)} type="button"><RotateCcw size={14} /> Tentar novamente</button>
                              ) : null}
                              <button className="button-danger" disabled={media.status === "uploading"} onClick={() => void removePendingMedia(media.id)} type="button"><Trash2 size={14} /> Remover</button>
                            </div>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                ) : null}

                {mediaLoading ? (
                  <div className="photo-empty-state media-loading-state"><LoaderCircle className="spin" size={18} /> Carregando mídias...</div>
                ) : selected && linkedImages.length ? (
                  <div className="property-media-grid">
                    {linkedImages.map((media, index) => {
                      const isImage = isPropertyImage(media);
                      return (
                        <article className="property-media-card" key={media.id}>
                          <div className="property-media-preview">
                            <button
                              aria-label={`Remover ${isImage ? "imagem" : "vídeo"} da lista`}
                              className="property-media-remove"
                              disabled={Boolean(imageBusy)}
                              onClick={() => void removeLinkedImage(media)}
                              title="Remover mídia"
                              type="button"
                            >
                              <X size={15} />
                            </button>
                            {isImage ? (
                              imageUrlFor(media) ? (
                                <button
                                  aria-label={`Ampliar ${media.original_name} (${imageVersionFor(media) === "optimized" ? "otimizada" : "original"})`}
                                  className="property-media-preview-open"
                                  onClick={() => openImageLightbox(media)}
                                  type="button"
                                >
                                  <img alt={media.original_name} src={imageUrlFor(media)} />
                                </button>
                              ) : (
                                <div className="property-media-placeholder">
                                  {mediaPreviewErrors[media.id] ? <span>{mediaPreviewErrors[media.id]}</span> : <><LoaderCircle className="spin" size={22} /><span>Carregando foto...</span></>}
                                </div>
                              )
                            ) : imageUrls[`detail:${media.id}`] ? (
                              <video controls preload="metadata" src={imageUrls[`detail:${media.id}`]} />
                            ) : (
                              <div className="property-media-placeholder video">
                                <Film size={28} />
                                <strong>{formatFileSize(media.original_size)}</strong>
                                {videoLoadProgress[media.id] !== undefined ? (
                                  <>
                                    <span>Carregando vídeo... {videoLoadProgress[media.id]}%</span>
                                    <div className="media-progress"><span style={{ width: `${videoLoadProgress[media.id]}%` }} /></div>
                                  </>
                                ) : (
                                  <button className="button-outline" onClick={() => void loadVideoContent(media)} type="button"><Play size={14} /> Carregar vídeo</button>
                                )}
                                {videoLoadErrors[media.id] ? <small className="media-error">{videoLoadErrors[media.id]}</small> : null}
                              </div>
                            )}
                            <span>{isImage ? "Foto" : "Vídeo"}</span>
                          </div>
                          <div className="property-media-card-body">
                            <strong>{media.original_name}</strong>
                            <span>{mediaStatusLabel(media)}{media.is_primary ? " · capa" : ""}</span>
                            {media.error ? <small>{media.error}</small> : null}
                            {isImage && media.derived_size ? (
                              <div aria-label="Versão exibida no preview" className="property-image-version-carousel">
                                <button aria-label="Exibir versão anterior" disabled={imageVersionFor(media) === "original"} onClick={() => selectImageVersion(media, "original")} type="button"><ChevronLeft size={15} /></button>
                                <div>
                                  <button className={imageVersionFor(media) === "original" ? "active" : ""} onClick={() => selectImageVersion(media, "original")} type="button">Original</button>
                                  <button className={imageVersionFor(media) === "optimized" ? "active" : ""} onClick={() => selectImageVersion(media, "optimized")} type="button">Otimizada</button>
                                </div>
                                <button aria-label="Exibir próxima versão" disabled={imageVersionFor(media) === "optimized"} onClick={() => selectImageVersion(media, "optimized")} type="button"><ChevronRight size={15} /></button>
                              </div>
                            ) : <div aria-hidden="true" className="property-image-version-placeholder" />}
                            <div className="property-media-card-actions property-media-reorder">
                              <button aria-label="Mover mídia para a esquerda" disabled={Boolean(imageBusy) || index === 0} onClick={() => void moveImage(index, -1)} title="Mover para a esquerda" type="button"><ChevronLeft size={16} /></button>
                              <button aria-label="Mover mídia para a direita" disabled={Boolean(imageBusy) || index === linkedImages.length - 1} onClick={() => void moveImage(index, 1)} title="Mover para a direita" type="button"><ChevronRight size={16} /></button>
                            </div>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                ) : pendingMedia.length === 0 ? (
                  <div className="photo-empty-state">Nenhuma mídia adicionada.</div>
                ) : null}
              </section>

              <div className="property-detail-actions">
                {formMessage ? <div className={formMessageKind === "error" ? "error-box" : "inline-feedback"}>{formMessage}</div> : null}
                {selected ? (
                  <>
                    <button className="button-outline" disabled={saving || mediaUploading} onClick={() => void changeStatus()} type="button">
                      {selected.status === "inactive" ? "Reativar" : "Inativar"}
                    </button>
                    {selected.status === "inactive" ? (
                      <button className="button-danger" disabled={saving || mediaUploading} onClick={() => void deleteSelected()} type="button">
                        Excluir definitivamente
                      </button>
                    ) : null}
                  </>
                ) : null}
                <button disabled={saving || mediaUploading || Boolean(imageBusy)} type="submit">
                  {saving ? "Salvando dados..." : mediaUploading ? "Enviando mídias..." : selected ? "Salvar alterações" : "Salvar imóvel"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {imageLightbox ? (
        <div className="modal-backdrop property-image-lightbox-backdrop" role="presentation">
          <section aria-label={`Visualização de ${imageLightbox.name}`} aria-modal="true" className="property-image-lightbox" role="dialog">
            <div className="property-image-lightbox-header">
              <div>
                <strong>{imageLightbox.name}</strong>
                <span>Versão {imageLightbox.version === "optimized" ? "otimizada" : "original"}</span>
              </div>
              <div>
                <a aria-label="Baixar imagem" className="icon-button" download={imageLightbox.name} href={imageLightbox.url}>
                  <Download size={18} />
                </a>
                <button aria-label="Fechar imagem" className="icon-button" onClick={() => setImageLightbox(null)} type="button">
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="property-image-lightbox-content">
              <img alt={imageLightbox.name} src={imageLightbox.url} />
            </div>
          </section>
        </div>
      ) : null}

      {isMediaModalOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section aria-modal="true" className="demand-modal property-media-upload-modal" role="dialog">
            <div className="modal-header">
              <div>
                <h2>Adicionar mídias</h2>
                <p>Os arquivos são preparados agora e vinculados ao imóvel somente quando você salvar.</p>
              </div>
              <button aria-label="Fechar mídias" className="icon-button" disabled={mediaUploading} onClick={() => setIsMediaModalOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            <div
              className={`property-media-dropzone${isMediaDropActive ? " active" : ""}`}
              onDragEnter={(event) => { event.preventDefault(); setIsMediaDropActive(true); }}
              onDragLeave={(event) => { event.preventDefault(); setIsMediaDropActive(false); }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleMediaDrop}
            >
              <ImagePlus size={32} />
              <strong>Arraste fotos e vídeos para esta área</strong>
              <span>ou escolha os arquivos no seu computador</span>
              <button className="button-outline" disabled={mediaUploading} onClick={() => mediaInputRef.current?.click()} type="button">
                Selecionar arquivos
              </button>
              <input
                accept={ACCEPTED_PROPERTY_MEDIA_TYPES.join(",")}
                hidden
                multiple
                onChange={(event) => {
                  addMediaFiles(Array.from(event.target.files ?? []));
                  event.target.value = "";
                }}
                ref={mediaInputRef}
                type="file"
              />
              <small>Fotos de até 10 MB e vídeos de até 100 MB. Máximo de 12 mídias.</small>
            </div>

            {pendingMedia.length ? (
              <div className="property-media-upload-list">
                {pendingMedia.map((media) => (
                  <div key={media.id}>
                    {media.file.type.startsWith("image/") ? <ImagePlus size={17} /> : <Film size={17} />}
                    <span><strong>{media.file.name}</strong><small>{formatFileSize(media.file.size)}</small></span>
                    <em className={media.status === "failed" ? "error" : ""}>
                      {media.status === "uploading" ? `${media.progress}%` : media.status === "ready" ? "Pronta" : media.status === "failed" ? "Falhou" : "Preparando"}
                    </em>
                    {media.status === "failed" ? <button aria-label={`Tentar novamente ${media.file.name}`} className="icon-button" disabled={mediaUploading} onClick={() => void retryMediaUpload(media)} type="button"><RotateCcw size={14} /></button> : null}
                    <button aria-label={`Remover ${media.file.name}`} className="icon-button" disabled={media.status === "uploading"} onClick={() => void removePendingMedia(media.id)} type="button"><Trash2 size={14} /></button>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="property-ai-actions">
              <span>{mediaUploading ? "Preparando mídias..." : `${pendingMedia.filter((media) => media.status === "ready").length} pronta(s) para salvar`}</span>
              <button disabled={mediaUploading} onClick={() => setIsMediaModalOpen(false)} type="button">Concluir</button>
            </div>
          </section>
        </div>
      ) : null}

      {isAiModalOpen && selected ? (
        <div className="modal-backdrop" role="presentation">
          <section aria-modal="true" className="demand-modal property-ai-modal" role="dialog">
            {optimizationProgress ? (
              <div aria-live="polite" className="property-ai-loading" role="status">
                <LoaderCircle className="spin" size={30} />
                <strong>{optimizationProgress}</strong>
                <span>A IA está preparando a nova versão. Não feche esta janela.</span>
              </div>
            ) : null}
            <div className="modal-header">
              <div>
                <h2>Otimizar fotos com IA</h2>
                <p>Selecione somente as imagens que deseja melhorar. Vídeos não participam deste processo.</p>
              </div>
              <button aria-label="Fechar otimização" className="icon-button" disabled={Boolean(imageBusy)} onClick={() => setIsAiModalOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            <div className="image-selection-actions">
              <button className="button-outline" disabled={Boolean(imageBusy) || selectedImageIds.length === optimizableImages.length} onClick={() => setSelectedImageIds(optimizableImages.map((image) => image.id))} type="button">Selecionar todas</button>
              <button className="button-outline" disabled={Boolean(imageBusy) || selectedImageIds.length === 0} onClick={() => setSelectedImageIds([])} type="button">Limpar seleção</button>
            </div>

            <div className="property-ai-image-grid">
              {optimizableImages.map((image) => (
                <label className={`property-ai-image-card${selectedImageIds.includes(image.id) ? " selected" : ""}`} key={image.id}>
                  <input
                    checked={selectedImageIds.includes(image.id)}
                    disabled={Boolean(imageBusy)}
                    onChange={() => setSelectedImageIds((current) => toggleImageOptimizationSelection(current, image.id))}
                    type="checkbox"
                  />
                  <img alt={image.original_name} src={imageUrls[`detail:${image.id}`]} />
                  <span>{image.original_name}</span>
                </label>
              ))}
            </div>

            <fieldset className="checkbox-group image-ai-options" disabled={Boolean(imageBusy)}>
              <legend>Ajustes desejados</legend>
              <p className="field-help">
                Os originais são preservados. Se nenhum ajuste for marcado, será aplicada uma melhoria geral conservadora.
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

            {aiMessage ? <div className={aiMessageKind === "error" ? "error-box" : "inline-feedback"}>{aiMessage}</div> : null}
            <div className="property-ai-actions">
              <span>{optimizationProgress ?? `${selectedImageIds.length} ${selectedImageIds.length === 1 ? "imagem selecionada" : "imagens selecionadas"}`}</span>
              <button className="button-outline" disabled={Boolean(imageBusy)} onClick={() => setIsAiModalOpen(false)} type="button">Cancelar</button>
              <button disabled={Boolean(imageBusy) || selectedImageIds.length === 0} onClick={optimizeSelectedImages} type="button">
                {optimizationProgress ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}
                {optimizationProgress ? "Otimizando..." : "Otimizar selecionadas"}
              </button>
            </div>
          </section>
        </div>
      ) : null}

    </section>
  );
}

function mediaStatusLabel(image: PropertyImage) {
  if (!isPropertyImage(image)) return "Vídeo original";
  if (image.status === "ready") return "Otimizada com IA";
  if (image.status === "processing") return "Otimização em andamento";
  if (image.status === "failed") return "Falha na otimização";
  return "Original salvo";
}

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`;
}
