import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { TERMS_VERSION } from "../src/legal/content.ts";

test("a versão dos termos é a mesma no front e no backend", () => {
  const routes = readFileSync(new URL("../../backend/app/modules/tenants/api/routes.py", import.meta.url), "utf8");
  const backend = routes.match(/TERMS_VERSION = "([^"]+)"/)?.[1];
  assert.equal(backend, TERMS_VERSION);
});
