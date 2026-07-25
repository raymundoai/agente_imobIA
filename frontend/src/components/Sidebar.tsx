import {
  BarChart3,
  Bot,
  ChevronsLeft,
  ChevronsRight,
  Hexagon,
  Home,
  MessageSquare,
  Settings,
  UserRoundCog,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { appRoutes, type AppPage, shouldHandleClientNavigation } from "../lib/appNavigation";

export const navigationItems = [
  { key: "dashboard", label: "Visão geral", icon: BarChart3 },
  { key: "conversations", label: "Conversas", icon: MessageSquare },
  { key: "contacts", label: "Contatos", icon: UserRoundCog },
  { key: "properties", label: "Imóveis", icon: Home },
  { key: "settings", label: "Configurações", icon: Settings },
] as const;

export function Sidebar({
  activePage,
  onNavigate,
}: {
  activePage: string;
  onNavigate: (page: AppPage) => void;
}) {
  const { tenantSlug } = useAuth();
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
          <Hexagon size={18} strokeWidth={2.4} />
        </div>
        <span>ImobIA</span>
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
        {navigationItems.map((item) => {
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
              <span>{item.label}</span>
            </a>
          );
        })}
      </nav>

      <div className="sidebar-user">
        <div className="avatar">
          <Bot size={16} />
        </div>
        <div>
          <strong>Operação</strong>
          <small>{tenantSlug || "empresa"}</small>
        </div>
      </div>
    </aside>
  );
}
