import { AlertCircle, CheckCircle2, Clock } from "lucide-react";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";

const items = [
  {
    status: "done",
    title: "Tenant e Agente IA",
    detail: "Formulários front conectados a tenant.settings para dados não sensíveis.",
  },
  {
    status: "done",
    title: "Usuários",
    detail: "Listagem, criação e edição de role/status usando /users.",
  },
  {
    status: "partial",
    title: "Integrações",
    detail: "Metadados configuráveis; secrets exigem backend criptografado.",
  },
  {
    status: "blocked",
    title: "Evolution QR Code",
    detail: "Botão e espaço de UI preparados; chamadas reais entram após vault de credenciais.",
  },
];

export function PendingFrontendPanel() {
  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Pendências do front</h2>
          <p>Mapa do que foi fechado agora e do que depende de backend/integração.</p>
        </div>
        <Badge variant="muted">controle</Badge>
      </div>
      <div className="pending-list">
        {items.map((item) => {
          const Icon =
            item.status === "done" ? CheckCircle2 : item.status === "partial" ? Clock : AlertCircle;
          return (
            <div className="pending-item" key={item.title}>
              <Icon size={18} />
              <div>
                <strong>{item.title}</strong>
                <span>{item.detail}</span>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
