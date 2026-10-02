import { useEffect, useState } from "react";
import { applyTheme, getActiveTheme, getStoredTheme, getSystemTheme, getThemeMediaQuery, storeTheme, type Theme } from "./theme";

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState(getActiveTheme);

  useEffect(() => {
    const mediaQuery = getThemeMediaQuery();
    function syncWithSystemTheme() {
      if (getStoredTheme()) return;
      const nextTheme = getSystemTheme();
      applyTheme(nextTheme);
      setTheme(nextTheme);
    }
    syncWithSystemTheme();
    mediaQuery.addEventListener("change", syncWithSystemTheme);
    return () => mediaQuery.removeEventListener("change", syncWithSystemTheme);
  }, []);

  function toggle() {
    const nextTheme = theme === "dark" ? "light" : "dark";
    storeTheme(nextTheme);
    setTheme(nextTheme);
  }

  return [theme, toggle];
}
