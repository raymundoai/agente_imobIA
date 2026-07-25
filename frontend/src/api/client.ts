import type { LoginResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("imobos:auth-expired"));
    }
    throw new ApiError(readErrorMessage(text), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function readErrorMessage(text: string) {
  if (!text) {
    return "Erro na API";
  }
  try {
    const parsed = JSON.parse(text) as { detail?: string; error?: string };
    if (parsed.error === "authentication_failed") {
      return "Sua sessão expirou. Entre novamente.";
    }
    return parsed.detail || parsed.error || text;
  } catch {
    return text;
  }
}

export function login(tenantSlug: string, email: string, password: string) {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ tenant_slug: tenantSlug, email, password }),
  });
}
