import assert from "node:assert/strict";
import test from "node:test";

import {
  atomicImageOrderSwap,
  imageOrderSwap,
  mergeSavedProperty,
  propertySaveFailureMessage,
  validateImageSelection,
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
  assert.deepEqual(atomicImageOrderSwap(images, 1, -1), [
    { id: "a", sort_order: 7 },
    { id: "b", sort_order: 3 },
    { id: "c", sort_order: 10 },
  ]);
});

test("seleção aceita apenas formatos e limites publicados", () => {
  assert.equal(
    validateImageSelection(0, [{ name: "foto.webp", type: "image/webp", size: 1024 }]),
    null,
  );
  assert.match(
    validateImageSelection(0, [{ name: "foto.gif", type: "image/gif", size: 1024 }]),
    /JPEG, PNG ou WebP/,
  );
  assert.match(
    validateImageSelection(12, [{ name: "foto.jpg", type: "image/jpeg", size: 1024 }]),
    /máximo 12/,
  );
});

test("falha parcial informa com precisão o que já foi persistido", () => {
  assert.match(propertySaveFailureMessage("timeout", false, false), /não foi salvo/);
  assert.match(
    propertySaveFailureMessage("timeout", false, false, true),
    /cadastro anterior permanece/,
  );
  assert.match(propertySaveFailureMessage("timeout", true, false), /imóvel foi salvo.*imagens/s);
  assert.match(
    propertySaveFailureMessage("timeout", true, true),
    /imóvel e as imagens originais foram salvos.*tratamento/s,
  );
});
