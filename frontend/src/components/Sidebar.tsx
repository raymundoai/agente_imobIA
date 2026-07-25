import {
  BarChart3,
  Bot,
  ChevronsLeft,
  ChevronsRight,
  Hexagon,
  Home,
  MessageSquare,
  Puzzle,
  Settings,
  UserRoundCog,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";

export const navigationItems = [
  { key: "dashboard", label: "Visão geral", icon: BarChart3 },
  { key: "conversations", label: "Conversas", icon: MessageSquare },
  { key: "contacts", label: "Contatos", icon: UserRoundCog },
  { key: "properties", label: "Imóveis", icon: Home },
  { key: "capture", label: "Buscador", icon: Puzzle },
  { key: "settings", label: "Configurações", icon: Settings },
] as const;

export function Sidebar({
  activePage,
  onNavigate,
}: {
  activePage: string;
  onNavigate: (page: string) => void;
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
            <button
              className={["nav-v2-item", isActive ? "active" : ""]
                .filter(Boolean)
                .join(" ")}
              key={item.key}
              onClick={() => {
                onNavigate(item.key);
              }}
              type="button"
            >
              <Icon size={17} />
              <span>{item.label}</span>
              {"highlight" in item && item.highlight ? <span className="nav-dot" /> : null}
            </button>
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
