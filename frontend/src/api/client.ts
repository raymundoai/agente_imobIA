import type { LoginResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
const AUTH_STORAGE_KEY = "imobos.auth.v1";

type StoredAuth = {
  token: string | null;
  refreshToken: string | null;
  tenantSlug: string;
};

let refreshPromise: Promise<string> | null = null;

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
  const response = await authenticatedFetch(path, options, token);
  return parseResponse<T>(response);
}

async function authenticatedFetch(
  path: string,
  options: RequestInit,
  token?: string | null,
) {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401 && token && path !== "/auth/refresh") {
    try {
      const refreshedToken = await refreshAccessToken();
      headers.set("Authorization", `Bearer ${refreshedToken}`);
      response = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (response.status === 401) {
        window.dispatchEvent(new CustomEvent("imobos:auth-expired"));
      }
    } catch {
      window.dispatchEvent(new CustomEvent("imobos:auth-expired"));
    }
  }
  return response;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(readErrorMessage(text), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function requestBlob(
  path: string,
  token?: string | null,
): Promise<Blob> {
  const headers = new Headers();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await authenticatedFetch(path, { headers }, token);
  if (!response.ok) throw new ApiError(readErrorMessage(await response.text()), response.status);
  return response.blob();
}

export async function requestBlobWithProgress(
  path: string,
  token: string | null | undefined,
  onProgress: (progress: number) => void,
  expectedBytes?: number,
): Promise<Blob> {
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await authenticatedFetch(path, { headers }, token);
  if (!response.ok) throw new ApiError(readErrorMessage(await response.text()), response.status);
  if (!response.body) return response.blob();

  const reader = response.body.getReader();
  const chunks: ArrayBuffer[] = [];
  const headerBytes = Number(response.headers.get("Content-Length") ?? 0);
  const totalBytes = headerBytes || expectedBytes || 0;
  let receivedBytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = new Uint8Array(value.byteLength);
    chunk.set(value);
    chunks.push(chunk.buffer);
    receivedBytes += value.byteLength;
    if (totalBytes > 0) {
      onProgress(Math.min(99, Math.round((receivedBytes / totalBytes) * 100)));
    }
  }
  onProgress(100);
  return new Blob(chunks, {
    type: response.headers.get("Content-Type") ?? "application/octet-stream",
  });
}

export function uploadFormDataWithProgress<T>(
  path: string,
  body: FormData,
  token: string | null | undefined,
  options: {
    onProgress: (progress: number) => void;
    timeoutMs: number;
  },
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.timeout = options.timeoutMs;
    xhr.responseType = "text";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        options.onProgress(Math.min(99, Math.round((event.loaded / event.total) * 100)));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        options.onProgress(100);
        try {
          resolve((xhr.responseText ? JSON.parse(xhr.responseText) : undefined) as T);
        } catch {
          reject(new ApiError("O sistema retornou uma resposta inválida para o upload.", xhr.status));
        }
        return;
      }
      if (xhr.status === 401) {
        window.dispatchEvent(new CustomEvent("imobos:auth-expired"));
      }
      reject(new ApiError(readErrorMessage(xhr.responseText), xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Falha de rede durante o upload.", 0));
    xhr.ontimeout = () => reject(new ApiError("O upload excedeu o tempo limite. Tente novamente.", 408));
    xhr.onabort = () => reject(new ApiError("O upload foi cancelado.", 0));
    xhr.send(body);
  });
}

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const stored = readStoredAuth();
    if (!stored?.refreshToken) throw new Error("Não foi possível renovar a sessão");
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: stored.refreshToken }),
    });
    if (!response.ok) throw new Error("Não foi possível renovar a sessão");
    const result = (await response.json()) as LoginResponse;
    const next: StoredAuth = {
      ...stored,
      token: result.access_token,
      refreshToken: result.refresh_token,
    };
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(
      new CustomEvent("imobos:auth-refreshed", { detail: result.access_token }),
    );
    return result.access_token;
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

function readStoredAuth(): StoredAuth | null {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAuth) : null;
  } catch {
    return null;
  }
}

function readErrorMessage(text: string) {
  if (!text) {
    return "Não foi possível concluir a solicitação.";
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; error?: string };
    if (parsed.error === "authentication_failed") {
      return "Sua sessão expirou. Entre novamente.";
    }
    if (typeof parsed.detail === "string") return userFacingMessage(parsed.detail);
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) return String(item.msg);
          return JSON.stringify(item);
        })
        .join(" ");
    }
    return userFacingMessage(parsed.error || text);
  } catch {
    return userFacingMessage(text);
  }
}

function userFacingMessage(message: string) {
  const translations: Record<string, string> = {
    "A contact with this phone already exists": "Já existe um contato com este telefone.",
    "Contact not found": "Contato não encontrado.",
    "Conversation not found": "Conversa não encontrada.",
    "Authentication required": "Entre novamente para continuar.",
    "Invalid access token": "Sua sessão expirou. Entre novamente.",
    "Insufficient permissions": "Seu perfil não permite realizar esta ação.",
    "Tenant not found": "Empresa não encontrada.",
    "User not found": "Usuário não encontrado.",
  };
  const normalized = message.replace(/^Value error,\s*/i, "");
  return translations[normalized] ?? normalized
    .replace(/\bbackend\b/gi, "sistema")
    .replace(/\bfrontend\b/gi, "tela")
    .replace(/\bAPI\b/g, "serviço");
}

export function login(tenantSlug: string, email: string, password: string) {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ tenant_slug: tenantSlug, email, password }),
  });
}

export function acceptInvitation(token: string, password: string) {
  return request<LoginResponse>("/auth/accept-invitation", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
}

export function changePassword(
  currentPassword: string,
  newPassword: string,
  token: string,
) {
  return request<LoginResponse>(
    "/auth/change-password",
    {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    },
    token,
  );
}
