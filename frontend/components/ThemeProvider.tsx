"use client";

import {
  createContext,
  useContext,
  useEffect,
  useEffectEvent,
  useState,
  type ReactNode,
} from "react";

import {
  applyTheme,
  getStoredThemePreference,
  resolveTheme,
  type ResolvedTheme,
  type ThemePreference,
} from "@/lib/theme";

type ThemeContextValue = {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>("light");
  const [resolved, setResolved] = useState<ResolvedTheme>("light");

  const syncFromPreference = useEffectEvent((next: ThemePreference) => {
    setPreferenceState(next);
    setResolved(applyTheme(next));
  });

  useEffect(() => {
    syncFromPreference(getStoredThemePreference());
  }, []);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== "agent-mesh-theme") return;
      syncFromPreference(getStoredThemePreference());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setPreference = (next: ThemePreference) => {
    syncFromPreference(next);
  };

  return (
    <ThemeContext.Provider value={{ preference, resolved, setPreference }}>
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
