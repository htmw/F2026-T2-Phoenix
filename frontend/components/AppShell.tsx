"use client";

import type { ReactNode } from "react";

import type { BackendStatus } from "@/lib/types";
import type { AiModeChip } from "@/lib/office";

export type NavTab = "home" | "agents" | "work" | "messages" | "settings";

const NAV: { id: NavTab; label: string; testId: string }[] = [
  { id: "home", label: "Home", testId: "tab-command" },
  { id: "agents", label: "Agents", testId: "tab-agents" },
  { id: "work", label: "Work", testId: "tab-work" },
  { id: "messages", label: "Messages", testId: "tab-activity" },
  { id: "settings", label: "Settings", testId: "tab-settings" },
];

function BackendBadge({ status }: { status: BackendStatus | null }) {
  if (!status) {
    return (
      <span className="badge" data-testid="backend-badge">
        checking…
      </span>
    );
  }
  if (!status.reachable) {
    return (
      <span className="badge err" data-testid="backend-badge">
        api down
      </span>
    );
  }
  return (
    <span
      className={`badge ${status.status === "ready" ? "ok" : "warn"}`}
      data-testid="backend-badge"
    >
      api {status.status}
    </span>
  );
}

function AiModeBadge({
  mode,
  freeOnly,
  onToggleFree,
}: {
  mode: AiModeChip;
  freeOnly: boolean;
  onToggleFree: () => void;
}) {
  if (mode === "configure") {
    return (
      <span className="chip err" title="Connect a provider in Settings">
        <span className="status-dot err" aria-hidden />
        No AI
      </span>
    );
  }
  if (mode === "offline") {
    return (
      <span className="chip warn" title="Simulated responses — connect a live provider for real models">
        <span className="status-dot warn" aria-hidden />
        Offline demo
      </span>
    );
  }
  return (
    <button
      type="button"
      className={`chip ${freeOnly ? "accent" : "warn"}`}
      onClick={onToggleFree}
      title={freeOnly ? "Free Only on — click to allow any model" : "Free Only off — click to prefer free/cheap"}
    >
      <span className={`status-dot ${freeOnly ? "ok" : "warn"}`} aria-hidden />
      Free AI {freeOnly ? "· On" : "· Off"}
    </button>
  );
}

export function AppShell({
  tab,
  onTab,
  status,
  aiMode,
  freeOnly,
  onToggleFree,
  onNewTask,
  children,
}: {
  tab: NavTab;
  onTab: (tab: NavTab) => void;
  status: BackendStatus | null;
  aiMode: AiModeChip;
  freeOnly: boolean;
  onToggleFree: () => void;
  onNewTask: () => void;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <header className="titlebar">
        <div className="brand-block">
          <h1 className="brand" data-testid="brand">
            Agent Office
          </h1>
          <p className="tagline">Intelligent agents. One brief. Clear results.</p>
        </div>
        <nav className="tabs" aria-label="Office sections" data-testid="office-tabs">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? "tab on" : "tab"}
              data-testid={item.testId}
              onClick={() => onTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="header-meta">
          <AiModeBadge mode={aiMode} freeOnly={freeOnly} onToggleFree={onToggleFree} />
          <BackendBadge status={status} />
          <button type="button" className="px-btn primary" onClick={onNewTask}>
            New task
          </button>
        </div>
      </header>
      {children}
    </div>
  );
}
