import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { applyTheme, getActiveTheme } from "./lib/theme";
import { PlatformApp } from "./platform/PlatformApp";
import "./styles.css";

applyTheme(getActiveTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PlatformApp />
  </StrictMode>,
);
