import assert from "node:assert/strict";
import test from "node:test";

import {
  imageOrderSwap,
  mergeSavedProperty,
  primaryReplacement,
} from "../src/lib/propertyMediaState.ts";

const property = (id, title = id) => ({ id, title });
const image = (id, sort_order, is_primary = false) => ({
  id,
  sort_order,
  is_primary,
});

test("cadastro persistido entra uma vez e falha parcial passa a atualizar o mesmo item", () => {
  const created = property("imovel-1", "Inicial");
  const afterCreate = mergeSavedProperty([], created, false);
  const updated = property("imovel-1", "Corrigido");
  const afterRetry = mergeSavedProperty(afterCreate, updated, true);

  assert.deepEqual(afterRetry, [updated]);
});

test("edição preserva a posição do imóvel na carteira", () => {
  const items = [property("a"), property("b"), property("c")];
  const saved = property("b", "B editado");

  assert.deepEqual(mergeSavedProperty(items, saved, true), [
    items[0],
    saved,
    items[2],
  ]);
});

test("reordenação troca posições sem criar ordem duplicada", () => {
  const images = [image("a", 3, true), image("b", 7), image("c", 10)];

  assert.deepEqual(imageOrderSwap(images, 1, -1), [
    { id: "b", sort_order: 3 },
    { id: "a", sort_order: 7 },
  ]);
  assert.equal(imageOrderSwap(images, 0, -1), null);
});

test("remoção só elege substituta quando a imagem removida era principal", () => {
  const images = [image("a", 0, true), image("b", 1)];

  assert.equal(primaryReplacement(images, images[1]), null);
  assert.equal(primaryReplacement(images, images[0])?.id, "b");
});
