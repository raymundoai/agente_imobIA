import { useEffect, useState } from "react";
import { request } from "../api/client";
import type { EvolutionWhatsappConnection } from "../api/types";
import { phoneIdentityKey } from "./ownNumber";

let cached: Promise<string | null> | null = null;

/** Identity key of the connected WhatsApp number, fetched once per page load. */
export function useOwnNumber(token: string | null): string | null {
  const [key, setKey] = useState<string | null>(null);
  useEffect(() => {
    if (!token) return;
    cached ??= request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/status", {}, token)
      .then((status) => (status.connected_phone ? phoneIdentityKey(status.connected_phone) : null))
      .catch(() => {
        cached = null;
        return null;
      });
    void cached.then(setKey);
  }, [token]);
  return key;
}
