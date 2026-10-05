import type { ReactNode } from "react";

export type ConnectionState = "connected" | "available" | "pending" | "soon";

const STATE_LABELS: Record<ConnectionState, string> = {
  connected: "Conectado",
  available: "Disponível",
  pending: "Interesse registrado",
  soon: "Em breve",
};

/** One card shape for channels and integrations: identity, state, one clear action. */
export function ConnectionCard({
  icon,
  name,
  description,
  state,
  action,
  onOpen,
  tone,
  brandIcon = false,
}: {
  icon: ReactNode;
  name: string;
  description: string;
  state: ConnectionState;
  action?: ReactNode;
  onOpen?: () => void;
  tone?: string;
  /** Third-party logos keep their own colours on a neutral tile. */
  brandIcon?: boolean;
}) {
  const body = (
    <>
      <div className="connection-card-top">
        <span className={brandIcon ? "connection-icon brand" : "connection-icon"} style={tone ? { background: tone, color: "#fff" } : undefined}>{icon}</span>
        <span className={`connection-state state-${state}`}>{STATE_LABELS[state]}</span>
      </div>
      <strong className="connection-name">{name}</strong>
      <p className="connection-description">{description}</p>
    </>
  );
  if (onOpen) {
    return (
      <button className={`connection-card is-${state}`} onClick={onOpen} type="button">
        {body}
      </button>
    );
  }
  return (
    <article className={`connection-card is-${state}`}>
      {body}
      {action ? <div className="connection-action">{action}</div> : null}
    </article>
  );
}

export function ConnectionSections({
  connected,
  others,
  othersTitle = "Disponíveis e em breve",
}: {
  connected: ReactNode[];
  others: ReactNode[];
  othersTitle?: string;
}) {
  return (
    <div className="connection-sections">
      {connected.length ? (
        <section>
          <h3 className="connection-section-title">Conectados</h3>
          <div className="connection-grid">{connected}</div>
        </section>
      ) : null}
      <section className={connected.length ? "connection-section-divided" : undefined}>
        <h3 className="connection-section-title">{othersTitle}</h3>
        <div className="connection-grid">{others}</div>
      </section>
    </div>
  );
}
