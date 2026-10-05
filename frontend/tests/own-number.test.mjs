import assert from "node:assert/strict";
import test from "node:test";

import { isOwnNumber, phoneIdentityKey } from "../src/lib/ownNumber.ts";

test("o número conectado é reconhecido com ou sem 55 e nono dígito", () => {
  const own = phoneIdentityKey("555191129452");
  for (const phone of ["5551991129452", "555191129452", "51991129452", "(51) 99112-9452"]) {
    assert.ok(isOwnNumber(phone, own), phone);
  }
  assert.equal(isOwnNumber("5551988887777", own), false);
  assert.equal(isOwnNumber("5551991129452", null), false);
});
