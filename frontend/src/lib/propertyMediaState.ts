import type { Property, PropertyImage } from "../api/types";

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

export function primaryReplacement(
  images: PropertyImage[],
  removed: PropertyImage,
) {
  if (!removed.is_primary) return null;
  return images.find((image) => image.id !== removed.id) ?? null;
}
