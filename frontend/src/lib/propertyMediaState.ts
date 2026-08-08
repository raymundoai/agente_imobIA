import type { Property, PropertyImage } from "../api/types";

export const MAX_PROPERTY_IMAGES = 12;
export const MAX_PROPERTY_IMAGE_BYTES = 10 * 1024 * 1024;
export const MAX_PROPERTY_VIDEO_BYTES = 100 * 1024 * 1024;
export const ACCEPTED_PROPERTY_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;
export const ACCEPTED_PROPERTY_VIDEO_TYPES = [
  "video/mp4",
  "video/quicktime",
  "video/webm",
] as const;
export const ACCEPTED_PROPERTY_MEDIA_TYPES = [
  ...ACCEPTED_PROPERTY_IMAGE_TYPES,
  ...ACCEPTED_PROPERTY_VIDEO_TYPES,
] as const;

export function isPropertyImage(
  media: Pick<PropertyImage, "media_type" | "original_content_type">,
) {
  return media.media_type === "image" || media.original_content_type.startsWith("image/");
}

export function validateMediaSelection(
  existingCount: number,
  files: Array<{ name: string; type: string; size: number }>,
) {
  const invalidType = files.find(
    (file) => !ACCEPTED_PROPERTY_MEDIA_TYPES.includes(
      file.type as (typeof ACCEPTED_PROPERTY_MEDIA_TYPES)[number],
    ),
  );
  if (invalidType) {
    return `${invalidType.name}: envie imagens JPEG, PNG ou WebP, ou vídeos MP4, MOV ou WebM.`;
  }
  const oversized = files.find((file) =>
    file.type.startsWith("video/")
      ? file.size > MAX_PROPERTY_VIDEO_BYTES
      : file.size > MAX_PROPERTY_IMAGE_BYTES,
  );
  if (oversized) {
    return oversized.type.startsWith("video/")
      ? `${oversized.name}: envie vídeos com até 100 MB.`
      : `${oversized.name}: envie imagens com até 10 MB.`;
  }
  if (existingCount + files.length > MAX_PROPERTY_IMAGES) {
    return `Cada imóvel aceita no máximo ${MAX_PROPERTY_IMAGES} mídias.`;
  }
  return null;
}

export function validateImageSelection(
  existingCount: number,
  files: Array<{ name: string; type: string; size: number }>,
) {
  return validateMediaSelection(existingCount, files);
}

export function propertySaveFailureMessage(
  reason: string,
  propertyPersisted: boolean,
  originalsPersisted: boolean,
  wasEditing = false,
) {
  if (originalsPersisted) {
    return `O imóvel e as mídias originais foram salvos, mas a galeria não pôde ser atualizada: ${reason} Feche e abra o cadastro novamente.`;
  }
  if (propertyPersisted) {
    return `O imóvel foi salvo, mas o envio das mídias não foi concluído: ${reason} Tente adicioná-las novamente neste cadastro.`;
  }
  if (wasEditing) {
    return `As alterações não foram salvas: ${reason} O cadastro anterior permanece disponível.`;
  }
  return `O imóvel não foi salvo: ${reason}`;
}

export function mergeSavedProperty(
  items: Property[],
  saved: Property,
  wasEditing: boolean,
) {
  return wasEditing
    ? items.map((item) => (item.id === saved.id ? saved : item))
    : [saved, ...items];
}

export function imageOrderSwap(
  images: PropertyImage[],
  index: number,
  direction: -1 | 1,
) {
  const current = images[index];
  const target = images[index + direction];
  if (!current || !target) return null;
  return [
    { id: current.id, sort_order: target.sort_order },
    { id: target.id, sort_order: current.sort_order },
  ] as const;
}

export function atomicImageOrderSwap(
  images: PropertyImage[],
  index: number,
  direction: -1 | 1,
) {
  const targetIndex = index + direction;
  if (!images[index] || !images[targetIndex]) return null;
  const reordered = [...images];
  [reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]];
  return reordered.map((image, sort_order) => ({ id: image.id, sort_order }));
}

export function toggleImageOptimizationSelection(
  selectedIds: string[],
  imageId: string,
) {
  return selectedIds.includes(imageId)
    ? selectedIds.filter((id) => id !== imageId)
    : [...selectedIds, imageId];
}

export function reconcileImageOptimizationSelection(
  selectedIds: string[],
  images: Array<Pick<PropertyImage, "id">>,
) {
  const availableIds = new Set(images.map((image) => image.id));
  return selectedIds.filter((id) => availableIds.has(id));
}
