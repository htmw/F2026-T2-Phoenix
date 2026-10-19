"use client";

import { createContext, useContext, useEffect, useSyncExternalStore, type ReactNode } from "react";

import {
  applyTheme,
  getStoredThemePreference,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ResolvedTheme,
  type ThemePreference,
} from "@/lib/theme";

type ThemeContextValue = {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);
const THEME_CHANGE = "agent-mesh-theme-change";

function serverPreference(): ThemePreference {
  return "light";
}

function subscribe(onChange: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY) onChange();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(THEME_CHANGE, onChange);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(THEME_CHANGE, onChange);
  };
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const preference = useSyncExternalStore(subscribe, getStoredThemePreference, serverPreference);

  useEffect(() => {
    applyTheme(preference);
  }, [preference]);

  const setPreference = (next: ThemePreference) => {
    applyTheme(next);
    window.dispatchEvent(new Event(THEME_CHANGE));
  };

  return (
    <ThemeContext.Provider value={{ preference, resolved: resolveTheme(preference), setPreference }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    return {
      preference: "light",
      resolved: "light",
      setPreference: () => undefined,
    };
  }
  return ctx;
}

/** Resolve without requiring a mounted preference (for one-off reads). */
export function useResolvedTheme(): ResolvedTheme {
  const { resolved } = useTheme();
  return resolved || resolveTheme("light");
}
