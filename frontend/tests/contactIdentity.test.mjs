import assert from "node:assert/strict";
import test from "node:test";

import {
  isValidContactIdentity,
  normalizeContactIdentity,
} from "../src/lib/contactIdentity.ts";

test("preserva WhatsApp brasileiro com código do país", () => {
  assert.equal(normalizeContactIdentity("+55 (11) 99999-0000"), "5511999990000");
  assert.equal(isValidContactIdentity("+55 (11) 99999-0000"), true);
});

test("preserva identidade Telegram sem convertê-la em telefone", () => {
  assert.equal(normalizeContactIdentity("telegram:321"), "telegram:321");
  assert.equal(isValidContactIdentity("telegram:321"), true);
});

test("rejeita identidades truncadas ou fora do contrato", () => {
  assert.equal(isValidContactIdentity("9999"), false);
  assert.equal(isValidContactIdentity("telegram:"), false);
});
