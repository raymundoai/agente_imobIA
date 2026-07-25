export type TokenClaims = {
  userId: string;
  tenantId: string;
  role: string;
};

export function getTokenClaims(token: string | null): TokenClaims | null {
  if (!token) {
    return null;
  }
  const [, payload] = token.split(".");
  if (!payload) {
    return null;
  }
  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = window.atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="));
    const claims = JSON.parse(json) as { sub?: string; tenant_id?: string; role?: string };
    if (!claims.sub || !claims.tenant_id || !claims.role) {
      return null;
    }
    return {
      userId: claims.sub,
      tenantId: claims.tenant_id,
      role: claims.role,
    };
  } catch {
    return null;
  }
}
