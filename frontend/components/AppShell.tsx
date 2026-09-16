"use client";

import type { ReactNode } from "react";

export type NavTab = "home" | "agents" | "work" | "messages" | "settings";

const NAV: { id: NavTab; label: string; testId: string }[] = [
  { id: "home", label: "Home", testId: "tab-command" },
  { id: "agents", label: "Agents", testId: "tab-agents" },
  { id: "work", label: "Work", testId: "tab-work" },
  { id: "messages", label: "Messages", testId: "tab-activity" },
  { id: "settings", label: "Settings", testId: "tab-settings" },
];

export function AppShell({
  tab,
  onTab,
  onNewTask,
  children,
}: {
  tab: NavTab;
  onTab: (tab: NavTab) => void;
  onNewTask: () => void;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <header className="titlebar">
        <div className="brand-row">
          <a href="/" className="brand-mark" aria-label="Agent Office marketing site" />
          <div className="brand-block">
            <h1 className="brand" data-testid="brand">
              Agent Office
            </h1>
            <p className="tagline">Autonomous specialists. One brief. Clear results.</p>
          </div>
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
          <a href="/" className="px-btn ghost">
            Overview
          </a>
          <button type="button" className="px-btn primary" onClick={onNewTask}>
            New task
          </button>
        </div>
      </header>
      {children}
    </div>
  );
}
