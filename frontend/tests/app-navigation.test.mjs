import assert from "node:assert/strict";
import test from "node:test";

import {
  appRoutes,
  isPlatformPath,
  pageFromPath,
  shouldHandleClientNavigation,
  subscribeToPageChanges,
} from "../src/lib/appNavigation.ts";

test("cada página operacional possui URL estável e aceita refresh", () => {
  for (const [page, path] of Object.entries(appRoutes)) {
    assert.equal(pageFromPath(path), page);
    assert.equal(pageFromPath(`${path === "/" ? "" : path}/`), page);
  }
});

test("rota desconhecida retorna para a visão geral sem expor admin", () => {
  assert.equal(pageFromPath("/recurso-removido-v2"), "dashboard");
  assert.equal(isPlatformPath("/recurso-removido-v2"), false);
});

test("acesso administrativo permanece reconhecido e isolado", () => {
  assert.equal(isPlatformPath("/platform"), true);
  assert.equal(isPlatformPath("/platform/clientes"), true);
  assert.equal(isPlatformPath("/plataform"), true);
  assert.equal(isPlatformPath("/configuracoes"), false);
});

test("popstate sincroniza a página do deep link e cleanup remove o listener", () => {
  const events = new EventTarget();
  const browser = {
    location: { pathname: "/conversas" },
    addEventListener: (...args) => events.addEventListener(...args),
    removeEventListener: (...args) => events.removeEventListener(...args),
  };
  const pages = [];
  const unsubscribe = subscribeToPageChanges((page) => pages.push(page), browser);

  events.dispatchEvent(new Event("popstate"));
  browser.location.pathname = "/imoveis";
  events.dispatchEvent(new Event("popstate"));
  unsubscribe();
  events.dispatchEvent(new Event("popstate"));

  assert.deepEqual(pages, ["conversations", "properties"]);
});

test("intercepta somente clique primário sem modificadores", () => {
  const plain = {
    button: 0, ctrlKey: false, metaKey: false, shiftKey: false,
    altKey: false, defaultPrevented: false,
  };
  assert.equal(shouldHandleClientNavigation(plain), true);
  for (const patch of [
    { button: 1 },
    { ctrlKey: true },
    { metaKey: true },
    { shiftKey: true },
    { altKey: true },
    { defaultPrevented: true },
  ]) {
    assert.equal(shouldHandleClientNavigation({ ...plain, ...patch }), false);
  }
});
