import type { Property, PropertyImage } from "../api/types";

export const MAX_PROPERTY_IMAGES = 12;
export const MAX_PROPERTY_IMAGE_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_PROPERTY_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;

export function validateImageSelection(
  existingCount: number,
  files: Array<{ name: string; type: string; size: number }>,
) {
  const invalid = files.find(
    (file) =>
      !ACCEPTED_PROPERTY_IMAGE_TYPES.includes(
        file.type as (typeof ACCEPTED_PROPERTY_IMAGE_TYPES)[number],
      ) || file.size > MAX_PROPERTY_IMAGE_BYTES,
  );
  if (invalid) return `${invalid.name}: envie JPEG, PNG ou WebP com até 10 MB.`;
  if (existingCount + files.length > MAX_PROPERTY_IMAGES) {
    return `Cada imóvel aceita no máximo ${MAX_PROPERTY_IMAGES} imagens.`;
  }
  return null;
}

export function propertySaveFailureMessage(
  reason: string,
  propertyPersisted: boolean,
  originalsPersisted: boolean,
  wasEditing = false,
) {
  if (originalsPersisted) {
    return `O imóvel e as imagens originais foram salvos, mas o tratamento não terminou: ${reason} Reprocesse as imagens vinculadas quando desejar.`;
  }
  if (propertyPersisted) {
    return `O imóvel foi salvo, mas o envio das imagens não foi concluído: ${reason} Tente adicionar as fotos novamente neste cadastro.`;
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
  const swap = imageOrderSwap(images, index, direction);
  if (!swap) return null;
  const orderById = new Map(swap.map((item) => [item.id, item.sort_order]));
  return images.map((image) => ({
    id: image.id,
    sort_order: orderById.get(image.id) ?? image.sort_order,
  }));
}
