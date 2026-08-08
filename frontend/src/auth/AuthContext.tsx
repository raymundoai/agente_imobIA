import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  acceptInvitation as apiAcceptInvitation,
  changePassword as apiChangePassword,
  login as apiLogin,
} from "../api/client";

type AuthContextValue = {
  token: string | null;
  tenantSlug: string;
  isAuthenticated: boolean;
  login: (tenantSlug: string, email: string, password: string) => Promise<void>;
  acceptInvitation: (invitationToken: string, password: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  logout: () => void;
};

const STORAGE_KEY = "imobos.auth.v1";

const AuthContext = createContext<AuthContextValue | null>(null);

function loadInitialAuth() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw
      ? (JSON.parse(raw) as {
          token: string | null;
          refreshToken: string | null;
          tenantSlug: string;
        })
      : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const initial = useMemo(loadInitialAuth, []);
  const [token, setToken] = useState<string | null>(initial?.token ?? null);
  const [tenantSlug, setTenantSlug] = useState(initial?.tenantSlug ?? "");

  const storeSession = useCallback((accessToken: string, refreshToken: string, slug: string) => {
    setToken(accessToken);
    setTenantSlug(slug);
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token: accessToken, refreshToken, tenantSlug: slug }),
    );
  }, []);

  const login = useCallback(async (slug: string, email: string, password: string) => {
    const result = await apiLogin(slug, email, password);
    storeSession(result.access_token, result.refresh_token, slug);
  }, [storeSession]);

  const acceptInvitation = useCallback(async (invitationToken: string, password: string) => {
    const result = await apiAcceptInvitation(invitationToken, password);
    if (!result.tenant_slug) throw new Error("O convite não informou a empresa vinculada.");
    storeSession(result.access_token, result.refresh_token, result.tenant_slug);
  }, [storeSession]);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    if (!token) throw new Error("Entre novamente para alterar a senha.");
    const result = await apiChangePassword(currentPassword, newPassword, token);
    storeSession(result.access_token, result.refresh_token, tenantSlug);
  }, [storeSession, tenantSlug, token]);

  const logout = useCallback(() => {
    setToken(null);
    setTenantSlug("");
    window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  useEffect(() => {
    window.addEventListener("imobos:auth-expired", logout);
    const updateToken = (event: Event) => {
      const refreshed = (event as CustomEvent<string>).detail;
      if (refreshed) setToken(refreshed);
    };
    window.addEventListener("imobos:auth-refreshed", updateToken);
    return () => {
      window.removeEventListener("imobos:auth-expired", logout);
      window.removeEventListener("imobos:auth-refreshed", updateToken);
    };
  }, [logout]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      tenantSlug,
      isAuthenticated: Boolean(token),
      login,
      acceptInvitation,
      changePassword,
      logout,
    }),
    [acceptInvitation, changePassword, login, logout, tenantSlug, token],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
