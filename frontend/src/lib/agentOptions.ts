/** Stored when no name is chosen; the backend then lets the agent introduce itself without one. */
export const DEFAULT_AGENT_NAME = "Agente de Leads";

/** Agent style options: one list for the setup wizard and for Settings, so both read the same. */
export const VOICE_TONES = [
  { value: "friendly", label: "Próximo e cordial" },
  { value: "professional", label: "Profissional" },
  { value: "consultative", label: "Consultivo" },
  { value: "informal", label: "Descontraído" },
] as const;

export const EMOJI_LEVELS = [
  { value: "none", label: "Não usar" },
  { value: "low", label: "Poucos" },
  { value: "moderate", label: "Moderados" },
] as const;
