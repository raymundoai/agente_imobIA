import assert from "node:assert/strict";
import test from "node:test";

import { formatPhone } from "../src/lib/format.ts";
import { propertyKindPhrase, propertyTypeLabel, purposeLabel } from "../src/lib/propertyLabels.ts";

test("telefone brasileiro aparece com DDD e hífen, com ou sem o 55", () => {
  assert.equal(formatPhone("5511947497989"), "(11) 94749-7989");
  assert.equal(formatPhone("51991129452"), "(51) 99112-9452");
  assert.equal(formatPhone("1133334444"), "(11) 3333-4444");
  assert.equal(formatPhone("+1 555 0100"), "+1 555 0100");
  assert.equal(formatPhone(null), "");
});

test("finalidade e tipo do imóvel aparecem em português", () => {
  assert.equal(purposeLabel("buy"), "Venda");
  assert.equal(purposeLabel("rent"), "Locação");
  assert.equal(propertyTypeLabel("sala_comercial"), "Sala comercial");
  assert.equal(propertyTypeLabel("galpao"), "Galpão");
  assert.equal(propertyTypeLabel("duplex_novo"), "Duplex novo");
  assert.equal(propertyKindPhrase("apartamento", "buy"), "Apartamento à venda");
  assert.equal(propertyKindPhrase("casa", "rent"), "Casa para locação");
  assert.equal(propertyKindPhrase("terreno", null), "Terreno");
});
