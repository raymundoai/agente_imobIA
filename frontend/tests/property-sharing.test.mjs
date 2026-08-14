import assert from "node:assert/strict";
import test from "node:test";

import {
  propertyShareFilename,
  propertyShareMimeType,
  shareablePropertyImages,
} from "../src/lib/propertySharing.ts";

test("compartilhamento envia somente fotos e respeita a ordem da galeria", () => {
  const images = [
    { id: "video", media_type: "video", sort_order: 0 },
    { id: "second", media_type: "image", sort_order: 2 },
    { id: "first", media_type: "image", sort_order: 1 },
  ];

  assert.deepEqual(
    shareablePropertyImages(images).map((image) => image.id),
    ["first", "second"],
  );
});

test("arquivo compartilhado usa o MIME real da versão otimizada", () => {
  assert.equal(propertyShareMimeType("image/png", "image/jpeg"), "image/png");
  assert.equal(propertyShareFilename("sala-original.jpeg", "image/png", 0), "sala-original.png");
});

test("normaliza image/jpg e usa os metadados originais como fallback", () => {
  assert.equal(propertyShareMimeType("", "image/jpg"), "image/jpeg");
  assert.equal(propertyShareMimeType("application/octet-stream", "image/webp"), "image/webp");
  assert.equal(propertyShareFilename("", "image/webp", 2), "foto-3.webp");
});
