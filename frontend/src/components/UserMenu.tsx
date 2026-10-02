import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AlertTriangle, Bell, CheckCircle2, ChevronLeft, ChevronsUpDown, LogOut, Moon, Settings, Sun } from "lucide-react";
import { request } from "../api/client";
import type { Tenant, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { getTokenClaims } from "../auth/tokenClaims";
import { loadOperationalAlerts } from "../lib/loadOperationalAlerts";
import { useTheme } from "../lib/useTheme";

type View = "menu" | "notifications";
type Position = { left: number; top?: number; bottom?: number; width: number };

export function UserMenu({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { logout, tenantSlug, token } = useAuth();
  const [theme, toggleTheme] = useTheme();
  const [user, setUser] = useState<User | null>(null);
  const [companyName, setCompanyName] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("menu");
  const [alerts, setAlerts] = useState<string[] | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    request<User>("/users/me", {}, token).then(setUser).catch(() => setUser(null));
    const tenantId = getTokenClaims(token)?.tenantId;
    if (tenantId) {
      request<Tenant>(`/tenants/${tenantId}`, {}, token)
        .then((tenant) => setCompanyName(tenant.settings.profile?.display_name || tenant.name))
        .catch(() => setCompanyName(null));
    }
    // Only when the account changes, not on each token refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantSlug]);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const place = () => {
      const rect = triggerRef.current!.getBoundingClientRect();
      const width = Math.max(rect.width, 248);
      const left = Math.min(rect.left, window.innerWidth - width - 8);
      // Open upwards from the sidebar footer; downwards when the trigger sits near the top (mobile).
      setPosition(
        rect.top > window.innerHeight / 2
          ? { left, bottom: window.innerHeight - rect.top + 8, width }
          : { left, top: rect.bottom + 8, width },
      );
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !triggerRef.current?.contains(target)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, view]);

  function close() {
    setOpen(false);
    setView("menu");
  }

  function showNotifications() {
    setView("notifications");
    setAlerts(null);
    loadOperationalAlerts(token).then(setAlerts).catch(() => setAlerts(["Não foi possível verificar os alertas."]));
  }

  const name = user?.name ?? "Minha conta";
  const dark = theme === "dark";

  return (
    <div className="sidebar-user">
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        className="user-menu-trigger"
        onClick={() => (open ? close() : setOpen(true))}
        ref={triggerRef}
        title={name}
        type="button"
      >
        <span className="avatar">{initials(name)}</span>
        <span className="user-menu-identity">
          <strong>{name}</strong>
          <small>{companyName ?? tenantSlug}</small>
        </span>
        <ChevronsUpDown className="user-menu-chevron" size={15} />
      </button>

      {open && position ? (
        <div
          aria-label="Menu da conta"
          className="user-menu"
          ref={menuRef}
          role="menu"
          style={{ left: position.left, top: position.top, bottom: position.bottom, width: position.width }}
        >
          {view === "menu" ? (
            <>
              <div className="user-menu-header">
                <strong>{name}</strong>
                {user?.email ? <small>{user.email}</small> : null}
              </div>
              <button className="user-menu-item" onClick={() => { close(); onOpenSettings(); }} role="menuitem" type="button">
                <Settings size={16} />
                Configurações
              </button>
              <button aria-checked={dark} className="user-menu-item" onClick={toggleTheme} role="menuitemcheckbox" type="button">
                {dark ? <Moon size={16} /> : <Sun size={16} />}
                Tema
                <span className="user-menu-value">{dark ? "Escuro" : "Claro"}</span>
              </button>
              <button className="user-menu-item" onClick={showNotifications} role="menuitem" type="button">
                <Bell size={16} />
                Notificações
              </button>
              <div className="user-menu-separator" role="separator" />
              <button className="user-menu-item danger" onClick={logout} role="menuitem" type="button">
                <LogOut size={16} />
                Sair
              </button>
            </>
          ) : (
            <>
              <button className="user-menu-item user-menu-back" onClick={() => setView("menu")} role="menuitem" type="button">
                <ChevronLeft size={16} />
                Notificações
              </button>
              <div className="user-menu-notifications" aria-live="polite">
                {alerts === null ? <p className="user-menu-empty">Verificando...</p> : null}
                {alerts?.length === 0 ? (
                  <p className="user-menu-empty">
                    <CheckCircle2 size={16} />
                    Nenhum alerta no momento.
                  </p>
                ) : null}
                {alerts?.map((alert) => (
                  <p className="user-menu-alert" key={alert}>
                    <AlertTriangle size={15} />
                    {alert}
                  </p>
                ))}
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}
