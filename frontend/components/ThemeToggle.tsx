"use client";

import { Moon, Sun } from "lucide-react";

import { useTheme } from "@/components/ThemeProvider";
import type { ThemePreference } from "@/lib/theme";

const OPTIONS: { id: ThemePreference; label: string; icon: typeof Sun }[] = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
];

export function ThemeToggle({
  className = "",
  compact = false,
}: {
  className?: string;
  /** Icon-only control for tight headers. */
  compact?: boolean;
}) {
  const { preference, setPreference } = useTheme();

  return (
    <div
      className={`theme-toggle ${compact ? "theme-toggle-compact" : ""} ${className}`.trim()}
      role="group"
      aria-label="Color theme"
    >
      {OPTIONS.map(({ id, label, icon: Icon }) => {
        const active = preference === id;
        return (
          <button
            key={id}
            type="button"
            className={active ? "theme-toggle-btn on" : "theme-toggle-btn"}
            aria-pressed={active}
            aria-label={`${label} theme`}
            title={label}
            onClick={() => setPreference(id)}
          >
            <Icon size={compact ? 15 : 16} strokeWidth={2} aria-hidden />
            {compact ? null : <span>{label}</span>}
          </button>
        );
      })}
    </div>
  );
}
