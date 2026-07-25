import { Instagram, Loader2, LogIn, MessageCircle, Music2, PlugZap, QrCode, Send, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { request } from "../../api/client";
import type { EvolutionWhatsappConnection, TelegramConnection, Tenant, TenantSettings } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";

type ChannelKey = "whatsapp" | "telegram" | "instagram" | "tiktok";

type ChannelConfig = {
  status: "connected" | "pending" | "disabled" | "disconnected";
  agents: Array<"leads" | "service">;
};

const defaultChannels: Record<ChannelKey, ChannelConfig> = {
  whatsapp: {
    status: "pending",
    agents: ["leads", "service"],
  },
  telegram: {
    status: "pending",
    agents: ["leads"],
  },
  instagram: {
    status: "disabled",
    agents: ["leads"],
  },
  tiktok: {
    status: "disabled",
    agents: ["leads"],
  },
};

export function ChannelsSettingsPanel({
  tenant,
  onTenantChange,
}: {
  tenant: Tenant | null;
  onTenantChange: (tenant: Tenant) => void;
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

  useEffect(() => {
    const savedChannels = tenant?.settings.channels as
      | Partial<Record<ChannelKey, Partial<ChannelConfig> & { agent?: "leads" | "service" }>>
      | undefined;
    setChannels({
      whatsapp: normalizeChannel(defaultChannels.whatsapp, savedChannels?.whatsapp),
      telegram: normalizeChannel(defaultChannels.telegram, savedChannels?.telegram),
      instagram: normalizeChannel(defaultChannels.instagram, savedChannels?.instagram),
      tiktok: normalizeChannel(defaultChannels.tiktok, savedChannels?.tiktok),
    });
  }, [tenant]);

  useEffect(() => {
    if (!token) {
      return undefined;
    }
    request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/status", {}, token)
      .then((connection) => {
        setWhatsappConnection(connection);
        updateChannel("whatsapp", { status: toChannelStatus(connection.status) });
      })
      .catch(() => undefined);
    request<TelegramConnection>("/integrations/telegram/status", {}, token)
      .then((connection) => {
        setTelegramConnection(connection);
        updateChannel("telegram", { status: toChannelStatus(connection.status) });
      })
      .catch(() => undefined);
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
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const settings: TenantSettings = {
        ...tenant.settings,
        channels,
      };
      const updated = await request<Tenant>(
        `/tenants/${claims.tenantId}/settings`,
        {
          method: "PATCH",
          body: JSON.stringify({ settings }),
        },
        token,
      );
      onTenantChange(updated);
      setMessage("Canais salvos.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao salvar canais.");
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
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao conectar Telegram.");
    }
  }

  return (
    <Card className="settings-panel-card">
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
        />
        <ChannelEditor
          channel="instagram"
          config={channels.instagram}
          icon={<Instagram size={20} />}
          title="Instagram"
          onChange={updateChannel}
        />
        <ChannelEditor
          channel="tiktok"
          config={channels.tiktok}
          icon={<Music2 size={20} />}
          title="TikTok"
          onChange={updateChannel}
        />
      </div>

      <div className="settings-actions">
        {message ? <span>{message}</span> : null}
        <button disabled={saving || !tenant} onClick={save} type="button">
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
}: {
  channel: ChannelKey;
  config: ChannelConfig;
  icon: ReactNode;
  onChange: (channel: ChannelKey, patch: Partial<ChannelConfig>) => void;
  onConnect?: () => void;
  title: string;
  connection?: (EvolutionWhatsappConnection | TelegramConnection) | null;
  connecting?: boolean;
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
        </div>
      </div>
      <div className="form-grid single">
        <fieldset className="checkbox-group">
          <legend>Agentes vinculados</legend>
          {agentOptions.map((agent) => (
            <label key={agent.key}>
              <input
                checked={config.agents.includes(agent.key)}
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
          disabled={channel === "instagram" || channel === "tiktok" || connecting}
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
            ? "Gerar QR Code"
            : channel === "telegram"
              ? "Configurar webhook"
              : channel === "tiktok"
                ? "Em planejamento"
                : "Conectar / fazer login"}
        </button>
        <span>
          {channel === "whatsapp"
            ? connection && "instance" in connection && connection.instance
              ? `Instância: ${connection.instance}`
              : "A conexão será feita pela Evolution API."
            : channel === "telegram"
              ? connection && "bot_username" in connection && connection.bot_username
                ? `Bot: @${connection.bot_username}`
                : "Configure o token do BotFather no backend."
            : channel === "instagram"
              ? "A conexão será ativada depois da criação do app Meta e configuração do login no backend."
              : "Canal planejado. A integração dependerá do acesso à API oficial do TikTok."}
        </span>
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

const agentOptions: Array<{ key: "leads" | "service"; label: string }> = [
  { key: "leads", label: "Agente de Leads" },
  { key: "service", label: "Agente de Atendimento" },
];

function normalizeChannel(
  defaults: ChannelConfig,
  saved?: Partial<ChannelConfig> & { agent?: "leads" | "service" },
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
                ? "WhatsApp conectado à Evolution API."
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
              <span>{connection.connected_phone || connection.connected_name || connection.instance}</span>
            </div>
          ) : (
            <div className="qr-placeholder">
              <span>Aguardando QR Code da Evolution.</span>
            </div>
          )}
        </div>

        <div className="settings-status">
          <Badge variant={connected ? "success" : "accent"}>
            {connected ? "Conectado" : "Aguardando leitura"}
          </Badge>
          {connection?.webhook_configured ? (
            <span>Webhook configurado.</span>
          ) : (
            <span>Webhook será configurado quando houver URL pública do backend.</span>
          )}
        </div>
      </div>
    </div>
  );
}
