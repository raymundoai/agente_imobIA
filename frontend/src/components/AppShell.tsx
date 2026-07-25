import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({
  activePage,
  children,
  onNavigate,
}: {
  activePage: string;
  children: ReactNode;
  onNavigate: (page: string) => void;
}) {
  return (
    <div className="app-shell-v2">
      <Sidebar activePage={activePage} onNavigate={onNavigate} />
      <div className="app-main-v2">
        <Topbar activePage={activePage} />
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
