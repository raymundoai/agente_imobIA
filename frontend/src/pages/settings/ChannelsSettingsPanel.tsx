import { Loader2, LogIn, MessageCircle, PlugZap, QrCode, Send, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { request } from "../../api/client";
import type { EvolutionWhatsappConnection, TelegramConnection, Tenant } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";

type ChannelKey = "whatsapp" | "telegram";

type ChannelConfig = {
  status: "connected" | "pending" | "disabled" | "disconnected";
  agents: Array<"leads">;
};

const defaultChannels: Record<ChannelKey, ChannelConfig> = {
  whatsapp: {
    status: "pending",
    agents: ["leads"],
  },
  telegram: {
    status: "pending",
    agents: ["leads"],
  },
};

export function ChannelsSettingsPanel({
  tenant,
  onTenantChange,
  onDirtyChange,
}: {
  tenant: Tenant | null;
  onTenantChange: (tenant: Tenant) => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { token } = useAuth();
  const claims = getTokenClaims(token);
  const [channels, setChannels] = useState<Record<ChannelKey, ChannelConfig>>(defaultChannels);
  const [whatsappConnection, setWhatsappConnection] =
    useState<EvolutionWhatsappConnection | null>(null);
  const [telegramConnection, setTelegramConnection] = useState<TelegramConnection | null>(null);
  const [qrModalOpen, setQrModalOpen] = useState(false);
  const [connectingWhatsapp, setConnectingWhatsapp] = useState(false);
  const [qrError, setQrError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error">("success");
  const [initialBindings, setInitialBindings] = useState<string | null>(null);
  const canManage = claims?.role === "admin";
  const canConnect = claims?.role === "admin" || claims?.role === "gestor";
  const currentBindings = JSON.stringify({
    whatsapp: channels.whatsapp.agents,
    telegram: channels.telegram.agents,
  });
  const dirty = initialBindings !== null && initialBindings !== currentBindings;

  useEffect(() => {
    const savedChannels = tenant?.settings.channels as
      | Partial<Record<ChannelKey, Partial<ChannelConfig> & { agent?: "leads" }>>
      | undefined;
    const nextChannels = {
      whatsapp: normalizeChannel(defaultChannels.whatsapp, savedChannels?.whatsapp),
      telegram: normalizeChannel(defaultChannels.telegram, savedChannels?.telegram),
    };
    setChannels(nextChannels);
    setInitialBindings(JSON.stringify({
      whatsapp: nextChannels.whatsapp.agents,
      telegram: nextChannels.telegram.agents,
    }));
  }, [tenant]);

  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  useEffect(() => {
    if (!token) {
      return undefined;
    }
    setStatusLoading(true);
    void Promise.allSettled([
      request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/status", {}, token),
      request<TelegramConnection>("/integrations/telegram/status", {}, token),
    ]).then(([whatsapp, telegram]) => {
      const errors: string[] = [];
      if (whatsapp.status === "fulfilled") {
        const connection = whatsapp.value;
        setWhatsappConnection(connection);
        updateChannel("whatsapp", { status: toChannelStatus(connection.status) });
      } else errors.push("WhatsApp");
      if (telegram.status === "fulfilled") {
        const connection = telegram.value;
        setTelegramConnection(connection);
        updateChannel("telegram", { status: toChannelStatus(connection.status) });
      } else errors.push("Telegram");
      setStatusError(errors.length ? `Não foi possível consultar: ${errors.join(" e ")}.` : null);
    }).finally(() => setStatusLoading(false));
    return undefined;
  }, [token]);

  useEffect(() => {
    if (!qrModalOpen || !token || whatsappConnection?.status === "connected") {
      return undefined;
    }
    const interval = window.setInterval(() => {
      request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/status", {}, token)
        .then((connection) => {
          setWhatsappConnection(connection);
          updateChannel("whatsapp", { status: toChannelStatus(connection.status) });
        })
        .catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(interval);
  }, [qrModalOpen, token, whatsappConnection?.status]);

  function updateChannel(channel: ChannelKey, patch: Partial<ChannelConfig>) {
    setChannels((current) => ({
      ...current,
      [channel]: { ...current[channel], ...patch },
    }));
  }

  async function save() {
    if (!claims || !tenant) {
      setMessage("Empresa não identificada no acesso atual.");
      setMessageKind("error");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const updated = await request<Tenant>(
        `/tenants/${claims.tenantId}/settings/channels`,
        {
          method: "PATCH",
          body: JSON.stringify({ channels }),
        },
        token,
      );
      onTenantChange(updated);
      setMessage("Canais salvos.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao salvar canais.");
      setMessageKind("error");
    } finally {
      setSaving(false);
    }
  }

  async function connectWhatsapp() {
    if (!token) {
      setQrError("Entre novamente para conectar o WhatsApp.");
      return;
    }
    setQrModalOpen(true);
    setConnectingWhatsapp(true);
    setQrError(null);
    try {
      const connection = await request<EvolutionWhatsappConnection>(
        "/integrations/evolution/whatsapp/connect",
        { method: "POST" },
        token,
      );
      setWhatsappConnection(connection);
      updateChannel("whatsapp", { status: toChannelStatus(connection.status) });
    } catch (error) {
      setQrError(error instanceof Error ? error.message : "Falha ao gerar QR Code.");
    } finally {
      setConnectingWhatsapp(false);
    }
  }

  async function connectTelegram() {
    if (!token) return;
    setMessage(null);
    try {
      const connection = await request<TelegramConnection>(
        "/integrations/telegram/connect", { method: "POST" }, token,
      );
      setTelegramConnection(connection);
      updateChannel("telegram", { status: toChannelStatus(connection.status) });
      setMessage(`Telegram @${connection.bot_username ?? "bot"} conectado.`);
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao conectar Telegram.");
      setMessageKind("error");
    }
  }

  return (
    <Card className="settings-panel-card">
      {statusLoading ? <div className="empty-state" aria-live="polite">Consultando canais...</div> : null}
      {statusError ? <div className="error-box" role="alert">{statusError}</div> : null}
      <div className="settings-panel-header">
        <div>
          <h2>Canais</h2>
          <p>Defina onde as conversas chegam e qual agente responde cada canal.</p>
        </div>
        <Badge variant="muted">
          <PlugZap size={13} />
          Entrada de conversas
        </Badge>
      </div>

      <div className="channel-grid">
        <ChannelEditor
          channel="telegram"
          config={channels.telegram}
          icon={<Send size={20} />}
          title="Telegram"
          onChange={updateChannel}
          onConnect={connectTelegram}
          connection={telegramConnection}
          canConnect={canConnect}
          canEdit={canManage}
        />
        <ChannelEditor
          channel="whatsapp"
          config={channels.whatsapp}
          icon={<MessageCircle size={20} />}
          title="WhatsApp"
          onChange={updateChannel}
          onConnect={connectWhatsapp}
          connection={whatsappConnection}
          connecting={connectingWhatsapp}
          canConnect={canConnect}
          canEdit={canManage}
        />
      </div>

      <div className="settings-actions">
        {message ? <span className={`settings-feedback ${messageKind}`} role={messageKind === "error" ? "alert" : "status"} aria-live="polite">{message}</span> : null}
        {dirty ? <span className="unsaved-indicator">Alterações não salvas</span> : null}
        <button disabled={saving || !tenant || !canManage || !dirty} onClick={save} type="button">
          {saving ? "Salvando..." : "Salvar canais"}
        </button>
      </div>
      {qrModalOpen ? (
        <WhatsappQrModal
          connection={whatsappConnection}
          error={qrError}
          loading={connectingWhatsapp}
          onClose={() => setQrModalOpen(false)}
          onRetry={connectWhatsapp}
        />
      ) : null}
    </Card>
  );
}

function ChannelEditor({
  channel,
  config,
  icon,
  onChange,
  onConnect,
  title,
  connection,
  connecting = false,
  canConnect,
  canEdit,
}: {
  channel: ChannelKey;
  config: ChannelConfig;
  icon: ReactNode;
  onChange: (channel: ChannelKey, patch: Partial<ChannelConfig>) => void;
  onConnect?: () => void;
  title: string;
  connection?: (EvolutionWhatsappConnection | TelegramConnection) | null;
  connecting?: boolean;
  canConnect: boolean;
  canEdit: boolean;
}) {
  return (
    <section className="channel-card">
      <div className="channel-card-header">
        <span className="settings-icon">{icon}</span>
        <div>
          <h3>{title}</h3>
          <Badge variant={config.status === "connected" ? "success" : config.status === "pending" ? "accent" : "muted"}>
            {statusLabels[config.status]}
          </Badge>
          {connection && "connected_phone" in connection && connection.connected_phone ? <span>{connection.connected_phone}</span> : null}
          {connection && "webhook_error" in connection && connection.webhook_error ? (
            <span className="integration-warning">A sincronização está temporariamente indisponível.</span>
          ) : null}
        </div>
      </div>
      <div className="form-grid single">
        <fieldset className="checkbox-group">
          <legend>Agentes vinculados</legend>
          {agentOptions.map((agent) => (
            <label key={agent.key}>
              <input
                checked={config.agents.includes(agent.key)}
                disabled={!canEdit}
                onChange={(event) => {
                  const nextAgents = event.target.checked
                    ? [...config.agents, agent.key]
                    : config.agents.filter((item) => item !== agent.key);
                  onChange(channel, { agents: nextAgents });
                }}
                type="checkbox"
              />
              {agent.label}
            </label>
          ))}
        </fieldset>
      </div>
      <div className="integration-actions">
        <button
          className="button-outline"
          disabled={connecting || !canConnect}
          onClick={onConnect}
          type="button"
        >
          {connecting ? (
            <Loader2 className="spin-icon" size={15} />
          ) : channel === "whatsapp" ? (
            <QrCode size={15} />
          ) : (
            <LogIn size={15} />
          )}
          {channel === "whatsapp"
            ? config.status === "connected" ? "Ver conexão" : "Gerar QR Code"
            : config.status === "connected" ? "Ver conexão" : "Conectar Telegram"}
        </button>
        {channel === "telegram" ? (
          <span>
            {connection && "bot_username" in connection && connection.bot_username
              ? `Bot: @${connection.bot_username}`
              : "A conexão usa a chave protegida configurada para esta empresa."}
          </span>
        ) : null}
      </div>
    </section>
  );
}

const statusLabels: Record<ChannelConfig["status"], string> = {
  connected: "Conectado",
  pending: "Pendente",
  disabled: "Desativado",
  disconnected: "Desconectado",
};

const agentOptions: Array<{ key: "leads"; label: string }> = [
  { key: "leads", label: "Agente de Leads" },
];

function normalizeChannel(
  defaults: ChannelConfig,
  saved?: Partial<ChannelConfig> & { agent?: "leads" },
): ChannelConfig {
  return {
    ...defaults,
    ...saved,
    agents: saved?.agents ?? (saved?.agent ? [saved.agent] : defaults.agents),
  };
}

function toChannelStatus(status: string): ChannelConfig["status"] {
  if (status === "connected") {
    return "connected";
  }
  if (status === "disconnected") {
    return "disconnected";
  }
  if (status === "not_configured") {
    return "pending";
  }
  return "pending";
}

function WhatsappQrModal({
  connection,
  error,
  loading,
  onClose,
  onRetry,
}: {
  connection: EvolutionWhatsappConnection | null;
  error: string | null;
  loading: boolean;
  onClose: () => void;
  onRetry: () => void;
}) {
  const connected = connection?.status === "connected";

  return (
    <div className="modal-backdrop">
      <div className="demand-modal compact whatsapp-qr-modal">
        <div className="modal-header">
          <div>
            <h2>Conectar WhatsApp</h2>
            <p>
              {connected
                ? "WhatsApp conectado."
                : "Abra o WhatsApp no celular e leia o QR Code para ativar o canal."}
            </p>
          </div>
          <button className="icon-button" onClick={onClose} type="button">
            <X size={17} />
          </button>
        </div>

        <div className="whatsapp-qr-content">
          {loading ? (
            <div className="qr-placeholder">
              <Loader2 className="spin-icon" size={26} />
              <span>Gerando QR Code...</span>
            </div>
          ) : error ? (
            <div className="qr-placeholder">
              <strong>Não foi possível gerar o QR Code.</strong>
              <span>{error}</span>
              <button className="button-outline" onClick={onRetry} type="button">
                Tentar novamente
              </button>
            </div>
          ) : connection?.qrcode && connection.qrcode.startsWith("data:image") ? (
            <img alt="QR Code do WhatsApp" className="whatsapp-qr-image" src={connection.qrcode} />
          ) : connection?.qrcode ? (
            <div className="qr-placeholder">
              <strong>Código de pareamento</strong>
              <code>{connection.qrcode}</code>
            </div>
          ) : connected ? (
            <div className="qr-placeholder success">
              <strong>Canal conectado</strong>
              <span>{connection.connected_phone || connection.connected_name || "WhatsApp conectado"}</span>
            </div>
          ) : (
            <div className="qr-placeholder">
              <span>Aguardando QR Code.</span>
            </div>
          )}
        </div>

        <div className="settings-status">
          <Badge variant={connected ? "success" : "accent"}>
            {connected ? "Conectado" : "Aguardando leitura"}
          </Badge>
          {connection?.webhook_configured ? (
            <span>Sincronização configurada.</span>
          ) : (
            <span>A sincronização será configurada quando o endereço público estiver disponível.</span>
          )}
        </div>
      </div>
    </div>
  );
}
