import { Globe } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { getTokenClaims } from "../../auth/tokenClaims";
import { Card } from "../../components/Card";
import { ChannelLogo } from "../../components/ChannelLogo";
import { ConnectionCard, ConnectionSections } from "../../components/ConnectionCard";
import { useWhatsappConnection, WhatsappConnectModal } from "../../components/WhatsappConnect";
import { formatPhone } from "../../lib/format";

const UPCOMING_CHANNELS = [
  { key: "telegram", name: "Telegram", icon: <ChannelLogo brand="telegram" />, description: "Atenda leads que chegam pelo seu bot do Telegram." },
  { key: "instagram", name: "Instagram Direct", icon: <ChannelLogo brand="instagram" />, description: "Responda mensagens do perfil da imobiliária." },
  { key: "messenger", name: "Facebook Messenger", icon: <ChannelLogo brand="messenger" />, description: "Conversas da página no Facebook, no mesmo lugar." },
  { key: "site", name: "Chat no site", icon: <Globe size={20} />, description: "Um balão de conversa para o site da imobiliária." },
];

export function ChannelsSettingsPanel() {
  const { token } = useAuth();
  const role = getTokenClaims(token)?.role;
  const canConnect = role === "admin" || role === "gestor";
  const whatsapp = useWhatsappConnection(token);
  const phone = whatsapp.connection?.connected_phone;

  const whatsappCard = (
    <ConnectionCard
      action={
        canConnect ? (
          <button className={whatsapp.connected ? "secondary-button" : "primary-button"} onClick={() => void whatsapp.connect()} type="button">
            {whatsapp.connected ? "Ver conexão" : "Conectar"}
          </button>
        ) : (
          <span className="connection-hint">Peça a um administrador para conectar.</span>
        )
      }
      description={
        whatsapp.connected
          ? `Recebendo mensagens em ${phone ? formatPhone(phone) : whatsapp.connection?.connected_name || "seu número"}.`
          : whatsapp.statusError
            ? "Não conseguimos consultar a conexão agora. Tente conectar de novo."
            : "Conecte o número da imobiliária lendo um QR Code."
      }
      icon={<ChannelLogo brand="whatsapp" />}
      key="whatsapp"
      brandIcon
      name="WhatsApp"
      state={whatsapp.checking ? "available" : whatsapp.connected ? "connected" : "available"}
    />
  );
  const upcoming = UPCOMING_CHANNELS.map(({ key, name, icon, description }) => (
    <ConnectionCard brandIcon={key !== "site"} description={description} icon={icon} key={key} name={name} state="soon" />
  ));

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Canais</h2>
          <p>Por onde os leads conversam com o agente de IA. As mensagens de todos os canais chegam em Conversas.</p>
        </div>
      </div>
      <ConnectionSections
        connected={whatsapp.connected ? [whatsappCard] : []}
        others={whatsapp.connected ? upcoming : [whatsappCard, ...upcoming]}
      />
      {whatsapp.modalOpen ? <WhatsappConnectModal whatsapp={whatsapp} /> : null}
    </Card>
  );
}
