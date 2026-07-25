export function formatNumber(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "—") {
    return "—";
  }
  return new Intl.NumberFormat("pt-BR").format(Number(value));
}

export function formatCurrency(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return new Intl.NumberFormat("pt-BR", {
    currency: "BRL",
    style: "currency",
    maximumFractionDigits: 0,
  }).format(numeric);
}

export function labelOrDash(value: string | null | undefined) {
  return value && value.trim() ? value : "—";
}
