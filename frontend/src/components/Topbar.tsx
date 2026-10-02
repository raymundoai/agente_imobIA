import { useMemo } from "react";
import { navigationItems } from "./Sidebar";
const subtitles: Record<string, string> = {
  dashboard: "Métricas principais da operação",
  conversations: "Atendimento de leads por WhatsApp e Telegram com IA e equipe humana",
  contacts: "Gestão de leads, clientes, tags e histórico de relacionamento",
  propertySearch: "Captação externa orientada pelas demandas dos clientes",
  settings: "Empresa, IA, canais, sistemas e equipe",
};

export function Topbar({ activePage }: { activePage: string }) {
  const title = useMemo(
    () => navigationItems.find((item) => item.key === activePage)?.label ?? "ImmobIA",
    [activePage],
  );
  const subtitle = subtitles[activePage];

  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
    </header>
  );
}
