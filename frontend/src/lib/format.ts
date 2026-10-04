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

export function formatDocument(value: string, type: "cpf" | "cnpj") {
  const digits = value.replace(/\D/g, "").slice(0, type === "cnpj" ? 14 : 11);
  if (type === "cpf") return digits.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  return digits.replace(/(\d{2})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1/$2").replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}

/** Brazilian phone for display: "(11) 94749-7989"; anything unexpected is returned as is. */
export function formatPhone(value: string | null | undefined) {
  if (!value) return "";
  let digits = value.replace(/\D/g, "");
  if (digits.length > 11 && digits.startsWith("55")) digits = digits.slice(2);
  if (digits.length === 11) return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
  if (digits.length === 10) return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  return value;
}
