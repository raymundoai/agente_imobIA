/**
 * The agency's own WhatsApp number (the one connected by QR code). Conversations and contacts
 * with it are the person talking to themselves, shown with a "Você" mark.
 */

/** Same key for every way one Brazilian number is written (mirrors the backend rule). */
export function phoneIdentityKey(value: string | null | undefined): string {
  let digits = String(value ?? "").replace(/\D/g, "");
  if ((digits.length === 12 || digits.length === 13) && digits.startsWith("55")) digits = digits.slice(2);
  if (digits.length === 11 && digits[2] === "9") digits = digits.slice(0, 2) + digits.slice(3);
  return digits;
}

export function isOwnNumber(phone: string | null | undefined, ownKey: string | null): boolean {
  return Boolean(ownKey && phone && phoneIdentityKey(phone) === ownKey);
}
