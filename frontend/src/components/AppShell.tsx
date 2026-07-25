import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import type { AppPage } from "../lib/appNavigation";

export function AppShell({
  activePage,
  children,
  onNavigate,
}: {
  activePage: string;
  children: ReactNode;
  onNavigate: (page: AppPage) => void;
}) {
  return (
    <div className="app-shell-v2">
      <a className="skip-link" href="#main-content">Pular para o conteúdo</a>
      <Sidebar activePage={activePage} onNavigate={onNavigate} />
      <div className="app-main-v2">
        <Topbar activePage={activePage} />
        <main className="page-content" id="main-content" tabIndex={-1}>{children}</main>
      </div>
    </div>
  );
}
