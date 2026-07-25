import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { login as apiLogin } from "../api/client";

type AuthContextValue = {
  token: string | null;
  tenantSlug: string;
  isAuthenticated: boolean;
  login: (tenantSlug: string, email: string, password: string) => Promise<void>;
  logout: () => void;
};

const STORAGE_KEY = "imobos.auth.v1";

const AuthContext = createContext<AuthContextValue | null>(null);

function loadInitialAuth() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as { token: string | null; tenantSlug: string }) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const initial = useMemo(loadInitialAuth, []);
  const [token, setToken] = useState<string | null>(initial?.token ?? null);
  const [tenantSlug, setTenantSlug] = useState(initial?.tenantSlug ?? "");

  const login = useCallback(async (slug: string, email: string, password: string) => {
    const result = await apiLogin(slug, email, password);
    setToken(result.access_token);
    setTenantSlug(slug);
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token: result.access_token, tenantSlug: slug }),
    );
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setTenantSlug("");
    window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  useEffect(() => {
    window.addEventListener("imobos:auth-expired", logout);
    return () => window.removeEventListener("imobos:auth-expired", logout);
  }, [logout]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      tenantSlug,
      isAuthenticated: Boolean(token),
      login,
      logout,
    }),
    [login, logout, tenantSlug, token],
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
