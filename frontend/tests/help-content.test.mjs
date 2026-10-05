import assert from "node:assert/strict";
import test from "node:test";

import { ARTICLES, SCREENS } from "../src/help/content.ts";

test("toda tela tem dica e só cita artigos que existem", () => {
  const ids = new Set(ARTICLES.map((article) => article.id));
  assert.equal(ids.size, ARTICLES.length, "ids de artigos repetidos");
  for (const [screen, help] of Object.entries(SCREENS)) {
    assert.ok(help.tip.length > 20, `${screen} sem dica`);
    for (const id of help.articles) assert.ok(ids.has(id), `${screen} cita artigo inexistente: ${id}`);
    for (const step of help.tour) assert.ok(step.target && step.title && step.text, `${screen} com passo incompleto`);
  }
});

test("links da central de ajuda apontam para telas do app", () => {
  for (const article of ARTICLES) {
    if (article.link) assert.match(article.link.href, /^\/(|conversas|contatos|imoveis|buscador-de-imoveis|configuracoes\?aba=[a-z]+)$/);
  }
});
