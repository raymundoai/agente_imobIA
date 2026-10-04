import assert from "node:assert/strict";
import test from "node:test";

import { identityFromProfile, identityToProfile, validateIdentity } from "../src/lib/businessIdentity.ts";

test("perfil novo começa em CPF com o nome de quem criou a conta", () => {
  const identity = identityFromProfile({}, "Maria Souza");
  assert.equal(identity.document_type, "cpf");
  assert.equal(identity.cpf_name, "Maria Souza");
  assert.equal(identity.business_type, null);
});

test("CPF e CNPJ guardam nome e número separados", () => {
  const identity = {
    ...identityFromProfile({}, "Maria Souza"),
    business_type: "agency",
    cpf_number: "123",
    cnpj_name: "Souza Imóveis Ltda.",
    cnpj_number: "11.222.333/0001-81",
    document_type: "cnpj",
  };
  assert.deepEqual(identityToProfile(identity), {
    business_type: "agency",
    document_type: "cnpj",
    document_number: "11222333000181",
    legal_name: "Souza Imóveis Ltda.",
  });
  assert.equal(identityToProfile({ ...identity, document_type: "cpf", cpf_number: "" }).legal_name, "Maria Souza");
});

test("perfil salvo com CNPJ volta para a razão social", () => {
  const identity = identityFromProfile(
    { document_type: "cnpj", document_number: "11222333000181", legal_name: "Souza Imóveis Ltda." },
    "",
  );
  assert.equal(identity.cnpj_number, "11.222.333/0001-81");
  assert.equal(identity.cnpj_name, "Souza Imóveis Ltda.");
});

test("documento é opcional, mas quando digitado precisa ser válido", () => {
  const blank = identityFromProfile({}, "Maria");
  assert.equal(validateIdentity(blank), null);
  assert.match(validateIdentity({ ...blank, cpf_number: "111.111.111-11" }), /CPF/);
});
