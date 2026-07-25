import { Bell, LogOut, Moon, Sun } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { applyTheme, getActiveTheme, getStoredTheme, getSystemTheme, getThemeMediaQuery, storeTheme } from "../lib/theme";
import { navigationItems } from "./Sidebar";

const subtitles: Record<string, string> = {
  dashboard: "Métricas principais da operação",
  capture: "Missões de captação, imóveis compatíveis e extensão do corretor",
  conversations: "Atendimento WhatsApp com IA e equipe humana",
  contacts: "Gestão de leads, clientes, tags e histórico de relacionamento",
  settings: "Canais, agentes, sistemas e equipe",
};

export function Topbar({ activePage }: { activePage: string }) {
  const { logout } = useAuth();
  const [theme, setTheme] = useState(getActiveTheme);
  const title = useMemo(
    () => navigationItems.find((item) => item.key === activePage)?.label ?? "ImobIA",
    [activePage],
  );
  const subtitle = subtitles[activePage];
  const dark = theme === "dark";

  useEffect(() => {
    const mediaQuery = getThemeMediaQuery();

    function syncWithSystemTheme() {
      if (getStoredTheme()) {
        return;
      }

      const nextTheme = getSystemTheme();
      applyTheme(nextTheme);
      setTheme(nextTheme);
    }

    syncWithSystemTheme();
    mediaQuery.addEventListener("change", syncWithSystemTheme);

    return () => mediaQuery.removeEventListener("change", syncWithSystemTheme);
  }, []);

  function toggleTheme() {
    const nextTheme = dark ? "light" : "dark";
    storeTheme(nextTheme);
    setTheme(nextTheme);
  }

  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      <div className="topbar-actions">
        <button aria-label="Notificações" className="icon-button" type="button">
          <Bell size={17} />
        </button>
        <button
          aria-label="Alternar tema"
          className="icon-button"
          onClick={toggleTheme}
          type="button"
        >
          {dark ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <button aria-label="Sair" className="icon-button" onClick={logout} type="button">
          <LogOut size={17} />
        </button>
      </div>
    </header>
  );
}
