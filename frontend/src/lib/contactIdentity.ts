export function normalizeContactIdentity(value: string) {
  const trimmed = value.trim();
  if (trimmed.toLowerCase().startsWith("telegram:")) {
    return `telegram:${trimmed.slice(trimmed.indexOf(":") + 1).trim()}`;
  }
  return trimmed.replace(/\D/g, "");
}

export function isValidContactIdentity(value: string) {
  const identity = normalizeContactIdentity(value);
  return /^telegram:\d{1,20}$/.test(identity) || /^\d{10,15}$/.test(identity);
}
