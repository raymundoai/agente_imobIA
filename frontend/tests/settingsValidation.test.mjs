import assert from "node:assert/strict";
import test from "node:test";

import {
  isValidBrazilianDocument,
  validateKnowledgeFile,
  validateNewUserForm,
} from "../src/lib/settingsValidation.ts";

test("valida CPF e CNPJ pelos dígitos verificadores", () => {
  assert.equal(isValidBrazilianDocument("529.982.247-25", "cpf"), true);
  assert.equal(isValidBrazilianDocument("529.982.247-24", "cpf"), false);
  assert.equal(isValidBrazilianDocument("04.252.011/0001-10", "cnpj"), true);
  assert.equal(isValidBrazilianDocument("11.111.111/1111-11", "cnpj"), false);
});

test("bloqueia arquivo incompatível, vazio ou maior que 10 MB", () => {
  assert.equal(validateKnowledgeFile({ name: "manual.pdf", size: 1024 }), null);
  assert.match(validateKnowledgeFile({ name: "planilha.xlsx", size: 1024 }), /TXT/);
  assert.match(validateKnowledgeFile({ name: "vazio.txt", size: 0 }), /vazio/);
  assert.match(validateKnowledgeFile({ name: "grande.pdf", size: 11 * 1024 * 1024 }), /10 MB/);
});

test("valida cadastro da equipe antes da chamada à API", () => {
  assert.deepEqual(validateNewUserForm({ name: "", email: "invalido", password: "123" }), {
    name: "Informe pelo menos 2 caracteres.",
    email: "Informe um email válido.",
    password: "Use pelo menos 12 caracteres.",
  });
  assert.deepEqual(validateNewUserForm({
    name: "Bruna Muller",
    email: "bruna@example.com",
    password: "senha-segura-123",
  }), {});
});
