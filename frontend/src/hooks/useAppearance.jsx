import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const themes = ["light", "dark", "system"];
const accents = ["purple", "blue", "emerald", "orange"];
const AppearanceContext = createContext(null);

const stored = (key, fallback, allowed) => {
  try {
    const value = window.localStorage.getItem(key);
    return allowed.includes(value) ? value : fallback;
  } catch (_) {
    return fallback;
  }
};

export function AppearanceProvider({ children }) {
  const [theme, setThemeState] = useState(() => stored("theme", "system", themes));
  const [accent, setAccentState] = useState(() => stored("accent-color", "purple", accents));
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true);

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const update = (event) => setSystemDark(event.matches);
    media?.addEventListener("change", update);
    return () => media?.removeEventListener("change", update);
  }, []);

  const effectiveTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme;
  useEffect(() => {
    document.documentElement.dataset.theme = effectiveTheme;
    document.documentElement.dataset.themePreference = theme;
    document.documentElement.dataset.accent = accent;
    document.documentElement.style.colorScheme = effectiveTheme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = effectiveTheme === "dark" ? "#07090f" : "#f6f7fb";
  }, [accent, effectiveTheme, theme]);

  const setTheme = useCallback((value) => {
    if (!themes.includes(value)) return;
    setThemeState(value);
    try { localStorage.setItem("theme", value); localStorage.removeItem("orbitlink-theme"); } catch (_) { /* no-op */ }
  }, []);
  const setAccent = useCallback((value) => {
    if (!accents.includes(value)) return;
    setAccentState(value);
    try { localStorage.setItem("accent-color", value); } catch (_) { /* no-op */ }
  }, []);

  const value = useMemo(() => ({ theme, accent, effectiveTheme, setTheme, setAccent }), [theme, accent, effectiveTheme, setTheme, setAccent]);
  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}

export function useAppearance() {
  return useContext(AppearanceContext);
}
