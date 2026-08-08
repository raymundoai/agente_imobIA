import { Bot, Building2, Cable, PlugZap, Settings, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "../api/client";
import type { Tenant } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { getTokenClaims } from "../auth/tokenClaims";
import { AgentsSettingsPanel } from "./settings/AgentsSettingsPanel";
import { ChannelsSettingsPanel } from "./settings/ChannelsSettingsPanel";
import { IntegrationsSettingsPanel } from "./settings/IntegrationsSettingsPanel";
import { TenantSettingsPanel } from "./settings/TenantSettingsPanel";
import { UsageSettingsPanel } from "./settings/UsageSettingsPanel";
import { UsersSettingsPanel } from "./settings/UsersSettingsPanel";

const tabs = [
  { key: "company", label: "Empresa", icon: Building2 },
  { key: "channels", label: "Canais", icon: PlugZap },
  { key: "integrations", label: "Integrações", icon: Cable },
  { key: "agents", label: "Configuração da IA", icon: Bot },
  { key: "users", label: "Equipe", icon: Users },
  { key: "usage", label: "Uso", icon: Settings },
] as const;

type SettingsTab = (typeof tabs)[number]["key"];

export function SettingsPage() {
  const { token } = useAuth();
  const claims = useMemo(() => getTokenClaims(token), [token]);
  const [activeTab, setActiveTab] = useState<SettingsTab>(() => settingsTabFromUrl());
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!claims?.tenantId) {
      setMessage("Empresa não identificada no acesso atual.");
      setLoading(false);
      return;
    }
    void request<Tenant>(`/tenants/${claims.tenantId}`, {}, token)
      .then((nextTenant) => {
        setTenant(nextTenant);
        setMessage(null);
        setLoading(false);
      })
      .catch((error) => { setMessage(error instanceof Error ? error.message : "Falha ao carregar empresa."); setLoading(false); });
  }, [claims?.tenantId, token]);

  useEffect(() => {
    const sync = () => {
      const nextTab = settingsTabFromUrl();
      if (dirty && nextTab !== activeTab && !window.confirm("Descartar as alterações não salvas?")) {
        const url = new URL(window.location.href);
        url.searchParams.set("aba", activeTab);
        window.history.replaceState({}, "", `${url.pathname}${url.search}`);
        return;
      }
      setDirty(false);
      setActiveTab(nextTab);
    };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [activeTab, dirty]);

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [dirty]);

  function selectTab(tab: SettingsTab) {
    if (tab === activeTab) return;
    if (dirty && !window.confirm("Descartar as alterações não salvas?")) return;
    const url = new URL(window.location.href);
    url.searchParams.set("aba", tab);
    window.history.pushState({}, "", `${url.pathname}${url.search}`);
    setDirty(false);
    setActiveTab(tab);
  }

  return (
    <section className="settings-page">
      {message ? <div className="error-box">{message}</div> : null}
      {loading ? <div className="empty-state large" aria-live="polite">Carregando configurações...</div> : null}

      {!loading && !message ? <div className="settings-layout">
        <aside className="settings-tabs">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                className={activeTab === tab.key ? "settings-tab active" : "settings-tab"}
                key={tab.key}
                aria-current={activeTab === tab.key ? "page" : undefined}
                onClick={() => selectTab(tab.key)}
                type="button"
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </aside>

        <div className="settings-panel">
          {activeTab === "company" ? (
            <TenantSettingsPanel onDirtyChange={setDirty} onTenantChange={setTenant} tenant={tenant} />
          ) : null}
          {activeTab === "channels" ? (
            <ChannelsSettingsPanel onDirtyChange={setDirty} onTenantChange={setTenant} tenant={tenant} />
          ) : null}
          {activeTab === "integrations" ? (
            <IntegrationsSettingsPanel onDirtyChange={setDirty} />
          ) : null}
          {activeTab === "agents" ? (
            <AgentsSettingsPanel onDirtyChange={setDirty} onTenantChange={setTenant} tenant={tenant} />
          ) : null}
          {activeTab === "users" ? <UsersSettingsPanel /> : null}
          {activeTab === "usage" ? <UsageSettingsPanel /> : null}
        </div>
      </div> : null}
    </section>
  );
}

function settingsTabFromUrl(): SettingsTab {
  const requested = new URLSearchParams(window.location.search).get("aba");
  if (requested === "knowledge") return "agents";
  return tabs.some((tab) => tab.key === requested) ? requested as SettingsTab : "company";
}
