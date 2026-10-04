const PROPERTY_TYPE_LABELS: Record<string, string> = {
  apartamento: "Apartamento",
  casa: "Casa",
  sobrado: "Sobrado",
  studio: "Studio",
  kitnet: "Kitnet",
  loft: "Loft",
  cobertura: "Cobertura",
  terreno: "Terreno",
  chacara: "Chácara",
  sitio: "Sítio",
  fazenda: "Fazenda",
  sala_comercial: "Sala comercial",
  loja: "Loja",
  galpao: "Galpão",
  predio: "Prédio",
};

const PURPOSE_LABELS: Record<string, string> = {
  buy: "Venda",
  rent: "Locação",
  both: "Venda e locação",
};

export function propertyTypeLabel(value: string | null | undefined) {
  if (!value) return "Imóvel";
  const known = PROPERTY_TYPE_LABELS[value.toLowerCase()];
  if (known) return known;
  const text = value.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function purposeLabel(value: string | null | undefined) {
  return value ? (PURPOSE_LABELS[value] ?? value) : "Finalidade não informada";
}

const OFFER_PHRASES: Record<string, string> = {
  buy: "à venda",
  rent: "para locação",
  both: "à venda ou locação",
};

/** "Apartamento à venda", "Casa para locação". */
export function propertyKindPhrase(type: string | null | undefined, purpose: string | null | undefined) {
  const offer = purpose ? OFFER_PHRASES[purpose] : undefined;
  return offer ? `${propertyTypeLabel(type)} ${offer}` : propertyTypeLabel(type);
}
