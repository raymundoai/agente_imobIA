import { Bot, Building2, Database, PlugZap, Settings, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "../api/client";
import type { Tenant } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { getTokenClaims } from "../auth/tokenClaims";
import { AgentsSettingsPanel } from "./settings/AgentsSettingsPanel";
import { ChannelsSettingsPanel } from "./settings/ChannelsSettingsPanel";
import { KnowledgeSettingsPanel } from "./settings/KnowledgeSettingsPanel";
import { TenantSettingsPanel } from "./settings/TenantSettingsPanel";
import { UsageSettingsPanel } from "./settings/UsageSettingsPanel";
import { UsersSettingsPanel } from "./settings/UsersSettingsPanel";

const tabs = [
  { key: "company", label: "Empresa", icon: Building2 },
  { key: "channels", label: "Canais", icon: PlugZap },
  { key: "agents", label: "Agentes", icon: Bot },
  { key: "knowledge", label: "Conhecimento", icon: Database },
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
    const sync = () => setActiveTab(settingsTabFromUrl());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  function selectTab(tab: SettingsTab) {
    const url = new URL(window.location.href);
    url.searchParams.set("aba", tab);
    window.history.pushState({}, "", `${url.pathname}${url.search}`);
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
            <TenantSettingsPanel onTenantChange={setTenant} tenant={tenant} />
          ) : null}
          {activeTab === "channels" ? (
            <ChannelsSettingsPanel onTenantChange={setTenant} tenant={tenant} />
          ) : null}
          {activeTab === "agents" ? (
            <AgentsSettingsPanel onTenantChange={setTenant} tenant={tenant} />
          ) : null}
          {activeTab === "knowledge" ? <KnowledgeSettingsPanel /> : null}
          {activeTab === "users" ? <UsersSettingsPanel /> : null}
          {activeTab === "usage" ? <UsageSettingsPanel /> : null}
        </div>
      </div> : null}
    </section>
  );
}

function settingsTabFromUrl(): SettingsTab {
  const requested = new URLSearchParams(window.location.search).get("aba");
  return tabs.some((tab) => tab.key === requested) ? requested as SettingsTab : "company";
}
