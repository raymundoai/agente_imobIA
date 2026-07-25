import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";

const navItems = [
  ["dashboard", "Dashboard"],
  ["conversations", "Conversas"],
  ["properties", "Imóveis"],
  ["settings", "Configurações"],
] as const;

type LayoutProps = {
  activePage: string;
  onNavigate: (page: string) => void;
  children: ReactNode;
};

export function Layout({ activePage, onNavigate, children }: LayoutProps) {
  const { logout, tenantSlug } = useAuth();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">IO</span>
          <div>
            <strong>ImobIA</strong>
            <small>{tenantSlug || "empresa"}</small>
          </div>
        </div>
        <nav>
          {navItems.map(([key, label]) => (
            <button
              className={activePage === key ? "nav-item active" : "nav-item"}
              key={key}
              onClick={() => onNavigate(key)}
              type="button"
            >
              {label}
            </button>
          ))}
        </nav>
        <button className="secondary-button" onClick={logout} type="button">
          Sair
        </button>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
