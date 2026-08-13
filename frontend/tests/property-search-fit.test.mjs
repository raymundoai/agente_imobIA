import assert from "node:assert/strict";
import test from "node:test";

import {
  compatibilityBucket,
  compatibilityCounts,
  matchesCompatibilityFilter,
} from "../src/lib/propertySearchFit.ts";

test("separa o ranking nas três faixas de compatibilidade", () => {
  assert.equal(compatibilityBucket(100), "perfect");
  assert.equal(compatibilityBucket(99), "high");
  assert.equal(compatibilityBucket(80), "high");
  assert.equal(compatibilityBucket(79), "lower");
  assert.deepEqual(compatibilityCounts([100, 100, 99, 80, 79, 40]), {
    perfect: 2,
    high: 2,
    lower: 2,
  });
});

test("cada faixa funciona como filtro e todos remove o filtro", () => {
  assert.equal(matchesCompatibilityFilter(100, "perfect"), true);
  assert.equal(matchesCompatibilityFilter(99, "perfect"), false);
  assert.equal(matchesCompatibilityFilter(80, "high"), true);
  assert.equal(matchesCompatibilityFilter(79, "high"), false);
  assert.equal(matchesCompatibilityFilter(40, "lower"), true);
  assert.equal(matchesCompatibilityFilter(40, "all"), true);
});
