import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { applyTheme, getActiveTheme } from "./lib/theme";
import "./styles.css";
import { isPlatformPath } from "./lib/appNavigation";

applyTheme(getActiveTheme());

const redirectToPlatform = isPlatformPath(window.location.pathname);

if (redirectToPlatform) {
  const configuredUrl = import.meta.env.VITE_PLATFORM_URL as string | undefined;
  const platformUrl = configuredUrl ?? `${window.location.protocol}//${window.location.hostname}:5174/`;
  window.location.replace(platformUrl);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {redirectToPlatform ? null : <AuthProvider><App /></AuthProvider>}
  </StrictMode>,
);
