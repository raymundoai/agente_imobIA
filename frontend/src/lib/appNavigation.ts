export const appRoutes = {
  dashboard: "/",
  conversations: "/conversas",
  contacts: "/contatos",
  properties: "/imoveis",
  propertySearch: "/buscador-de-imoveis",
  settings: "/configuracoes",
} as const;

export type AppPage = keyof typeof appRoutes;

export function pageFromPath(pathname: string): AppPage {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  return (Object.entries(appRoutes).find(([, path]) => path === normalized)?.[0] ??
    "dashboard") as AppPage;
}

export function isPlatformPath(pathname: string) {
  return /^\/(platform|plataform)(\/|$)/.test(pathname);
}

export type NavigationClick = {
  button: number;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  defaultPrevented: boolean;
};

export function shouldHandleClientNavigation(event: NavigationClick) {
  return (
    event.button === 0 &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey &&
    !event.altKey &&
    !event.defaultPrevented
  );
}

export function navigateToPage(page: AppPage) {
  const path = appRoutes[page];
  if (window.location.pathname !== path) {
    window.history.pushState({ page }, "", path);
  }
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function subscribeToPageChanges(
  onPage: (page: AppPage) => void,
  browser: Pick<Window, "addEventListener" | "removeEventListener" | "location"> = window,
) {
  const sync = () => onPage(pageFromPath(browser.location.pathname));
  browser.addEventListener("popstate", sync);
  return () => browser.removeEventListener("popstate", sync);
}
