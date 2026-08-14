import type { PropertyImage } from "../api/types";

const imageExtensions: Record<string, string> = {
  "image/jpeg": ".jpg",
  "image/png": ".png",
  "image/webp": ".webp",
};

export function shareablePropertyImages(images: PropertyImage[]) {
  return images
    .filter((image) => image.media_type === "image")
    .sort((left, right) => left.sort_order - right.sort_order);
}

export function propertyShareMimeType(blobType: string, originalType: string) {
  const normalizedBlob = normalizeMimeType(blobType);
  if (normalizedBlob in imageExtensions) return normalizedBlob;
  const normalizedOriginal = normalizeMimeType(originalType);
  return normalizedOriginal in imageExtensions ? normalizedOriginal : "image/jpeg";
}

export function propertyShareFilename(originalName: string, mimeType: string, index: number) {
  const trimmed = originalName.trim();
  const stem = (trimmed || `foto-${index + 1}`).replace(/\.[a-z0-9]+$/i, "");
  return `${stem}${imageExtensions[mimeType] ?? ".jpg"}`;
}

function normalizeMimeType(value: string) {
  const normalized = value.split(";", 1)[0].trim().toLowerCase();
  return normalized === "image/jpg" ? "image/jpeg" : normalized;
}
