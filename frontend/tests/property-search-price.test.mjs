import assert from "node:assert/strict";
import test from "node:test";

import { searchPricePresentation } from "../src/lib/propertySearchPrice.ts";

const both = {
  purpose: "both",
  price: "14500",
  sale_price: "3390000",
  rent_price: "14500",
};

test("busca de aluguel destaca aluguel e informa venda como alternativa", () => {
  assert.deepEqual(searchPricePresentation("rent", both), {
    primary: "14500",
    primaryLabel: "Aluguel",
    alternative: "3390000",
    alternativeLabel: "Também à venda por",
  });
});

test("busca de compra destaca venda e informa aluguel como alternativa", () => {
  assert.deepEqual(searchPricePresentation("buy", both), {
    primary: "3390000",
    primaryLabel: "Venda",
    alternative: "14500",
    alternativeLabel: "Também para aluguel por",
  });
});

test("não usa preço de venda como destaque quando o aluguel está ausente", () => {
  assert.equal(
    searchPricePresentation("rent", {
      purpose: "buy",
      price: "800000",
      sale_price: "800000",
      rent_price: null,
    }).primary,
    null,
  );
});
