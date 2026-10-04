import {
  BarChart3,
  ChevronsLeft,
  ChevronsRight,
  Home,
  MessageSquare,
  Search,
  Settings,
  UserRoundCog,
} from "lucide-react";
import { useEffect, useState } from "react";
import { appRoutes, type AppPage, shouldHandleClientNavigation } from "../lib/appNavigation";
import { UserMenu } from "./UserMenu";
import { BrandMark } from "./BrandMark";

export const navigationItems = [
  { key: "dashboard", label: "Visão geral", short: "Início", icon: BarChart3 },
  { key: "conversations", label: "Conversas", short: "Conversas", icon: MessageSquare },
  { key: "contacts", label: "Contatos", short: "Contatos", icon: UserRoundCog },
  { key: "properties", label: "Imóveis", short: "Imóveis", icon: Home },
  { key: "propertySearch", label: "Buscador de imóveis", short: "Buscador", icon: Search },
  { key: "settings", label: "Configurações", short: "Ajustes", icon: Settings },
] as const;

// Settings is reached from the account menu in the sidebar footer.
const sidebarItems = navigationItems.filter((item) => item.key !== "settings");

export function Sidebar({
  activePage,
  onNavigate,
}: {
  activePage: string;
  onNavigate: (page: AppPage) => void;
}) {
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem("imobos.sidebar.collapsed") === "true",
  );

  useEffect(() => {
    window.localStorage.setItem("imobos.sidebar.collapsed", String(collapsed));
  }, [collapsed]);

  return (
    <aside className={collapsed ? "sidebar-v2 collapsed" : "sidebar-v2"}>
      <div className="brand-v2">
        <div className="brand-icon">
          <BrandMark />
        </div>
        <span>ImmobIA</span>
        <button
          aria-label={collapsed ? "Exibir menu" : "Esconder menu"}
          className="sidebar-toggle"
          onClick={() => setCollapsed((current) => !current)}
          title={collapsed ? "Exibir menu" : "Esconder menu"}
          type="button"
        >
          {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
        </button>
      </div>

      <nav className="nav-v2">
        {sidebarItems.map((item) => {
          const Icon = item.icon;
          const isActive = activePage === item.key;
          return (
            <a
              aria-current={isActive ? "page" : undefined}
              className={["nav-v2-item", isActive ? "active" : ""]
                .filter(Boolean)
                .join(" ")}
              key={item.key}
              href={appRoutes[item.key]}
              onClick={(event) => {
                if (!shouldHandleClientNavigation(event)) return;
                event.preventDefault();
                onNavigate(item.key);
              }}
            >
              <Icon size={17} />
              <span className="nav-label">{item.label}</span>
              <span aria-hidden="true" className="nav-short">{item.short}</span>
            </a>
          );
        })}
      </nav>

      <UserMenu onOpenSettings={() => onNavigate("settings")} />
    </aside>
  );
}
