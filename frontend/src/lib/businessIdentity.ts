import type { TenantSettings } from "../api/types";
import { formatDocument } from "./format.ts";
import { isValidBrazilianDocument } from "./settingsValidation.ts";

export type BusinessType = "broker" | "agency";
type Profile = NonNullable<TenantSettings["profile"]>;

/** Each document keeps its own name and number, so switching CPF/CNPJ never mixes them. */
export type BusinessIdentity = {
  business_type: BusinessType | null;
  document_type: "cpf" | "cnpj";
  cpf_name: string;
  cpf_number: string;
  cnpj_name: string;
  cnpj_number: string;
};

export function identityFromProfile(profile: Profile, personName: string): BusinessIdentity {
  const isCnpj = profile.document_type === "cnpj";
  return {
    business_type: profile.business_type ?? null,
    document_type: isCnpj ? "cnpj" : "cpf",
    cpf_name: !isCnpj && profile.legal_name ? profile.legal_name : personName,
    cpf_number: !isCnpj ? formatDocument(profile.document_number ?? "", "cpf") : "",
    cnpj_name: isCnpj ? profile.legal_name ?? "" : "",
    cnpj_number: isCnpj ? formatDocument(profile.document_number ?? "", "cnpj") : "",
  };
}

export function identityToProfile(identity: BusinessIdentity): Partial<Profile> {
  const isCnpj = identity.document_type === "cnpj";
  const digits = (isCnpj ? identity.cnpj_number : identity.cpf_number).replace(/\D/g, "");
  const name = (isCnpj ? identity.cnpj_name : identity.cpf_name).trim();
  return {
    business_type: identity.business_type ?? undefined,
    document_type: digits ? identity.document_type : undefined,
    document_number: digits || undefined,
    legal_name: name || undefined,
  };
}

export function validateIdentity(identity: BusinessIdentity): string | null {
  const type = identity.document_type;
  const digits = (type === "cnpj" ? identity.cnpj_number : identity.cpf_number).replace(/\D/g, "");
  if (digits && !isValidBrazilianDocument(digits, type)) {
    return `Confira o ${type.toUpperCase()}: o número digitado não é válido.`;
  }
  return null;
}

