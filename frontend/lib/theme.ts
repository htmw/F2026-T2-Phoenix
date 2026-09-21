export type ThemePreference = "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "agent-mesh-theme";

export function isThemePreference(value: string | null | undefined): value is ThemePreference {
  return value === "light" || value === "dark";
}

/** Map legacy "auto" (and anything else) to a concrete light/dark choice. */
function coercePreference(raw: string | null | undefined): ThemePreference {
  if (raw === "light" || raw === "dark") return raw;
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function getStoredThemePreference(): ThemePreference {
  if (typeof window === "undefined") return "light";
  try {
    return coercePreference(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "light";
  }
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference;
}

/** Apply theme attributes on <html> and persist the choice. */
export function applyTheme(preference: ThemePreference): ResolvedTheme {
  const resolved = resolveTheme(preference);
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.dataset.themePreference = preference;
  root.style.colorScheme = resolved;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* private mode */
  }
  return resolved;
}

/** Inline boot script — keep in sync with applyTheme / storage key. */
export const THEME_BOOT_SCRIPT = `(function(){try{var k=${JSON.stringify(THEME_STORAGE_KEY)};var p=localStorage.getItem(k);if(p!=="light"&&p!=="dark"){p=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";try{localStorage.setItem(k,p);}catch(e){}}var r=document.documentElement;r.dataset.theme=p;r.dataset.themePreference=p;r.style.colorScheme=p;}catch(e){}})();`;
