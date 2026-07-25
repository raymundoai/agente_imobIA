import assert from "node:assert/strict";
import test from "node:test";

import { runWithLoading } from "../src/lib/asyncState.ts";
import { jobsUnavailableAlert } from "../src/lib/operationalAlerts.ts";

test("indisponibilidade de jobs nunca é tratada como operação verde", () => {
  assert.match(jobsUnavailableAlert(), /Não foi possível verificar/);
  assert.match(jobsUnavailableAlert(403), /perfil não permite verificar/);
});

test("carregamento administrativo sempre termina quando APIs falham", async () => {
  const loading = [];
  const errors = [];
  const result = await runWithLoading(
    (value) => loading.push(value),
    async () => {
      throw new Error("API indisponível");
    },
    (error) => errors.push(error.message),
  );

  assert.equal(result, undefined);
  assert.deepEqual(loading, [true, false]);
  assert.deepEqual(errors, ["API indisponível"]);
});

test("carregamento administrativo também termina após sucesso", async () => {
  const loading = [];
  const result = await runWithLoading(
    (value) => loading.push(value),
    async () => "ok",
    () => assert.fail("não deveria falhar"),
  );

  assert.equal(result, "ok");
  assert.deepEqual(loading, [true, false]);
});
