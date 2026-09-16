"use client";

import { FormEvent } from "react";

import type { AgentSummary, RoutingStrategy } from "@/lib/types";

const EXAMPLES = [
  "Find security vulnerabilities in the payments service",
  "Fix the login handler and write tests for it",
  "Research this topic and create a summary",
];

export function TaskComposer({
  request,
  onRequest,
  busy,
  offlineDemo,
  noModels,
  onConfigure,
  onCheckAgain,
  advancedOpen,
  onToggleAdvanced,
  pickAgents,
  onPickAgents,
  agents,
  selectedAgents,
  onToggleAgent,
  routingStrategy,
  onRoutingStrategy,
  sharedModel,
  onSharedModel,
  modelOverrides,
  onModelOverride,
  modelOptions,
  requireApproval,
  onRequireApproval,
  maxCost,
  onMaxCost,
  freeOnlyBlocked,
  onSubmit,
  compact = false,
}: {
  request: string;
  onRequest: (value: string) => void;
  busy: boolean;
  offlineDemo: boolean;
  noModels: boolean;
  onConfigure: () => void;
  onCheckAgain: () => void;
  advancedOpen: boolean;
  onToggleAdvanced: () => void;
  pickAgents: boolean;
  onPickAgents: (value: boolean) => void;
  agents: AgentSummary[];
  selectedAgents: string[];
  onToggleAgent: (id: string) => void;
  routingStrategy: RoutingStrategy;
  onRoutingStrategy: (value: RoutingStrategy) => void;
  sharedModel: string;
  onSharedModel: (value: string) => void;
  modelOverrides: Record<string, string>;
  onModelOverride: (agentId: string, value: string) => void;
  modelOptions: { id: string; label: string }[];
  requireApproval: boolean;
  onRequireApproval: (value: boolean) => void;
  maxCost: string;
  onMaxCost: (value: string) => void;
  freeOnlyBlocked: string | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  compact?: boolean;
}) {
  const roster = pickAgents ? selectedAgents : agents.map((agent) => agent.id);

  return (
    <section className={`panel composer-hero ${compact ? "composer-compact" : ""}`}>
      {!compact && (
        <>
          <h2>What should the office take on?</h2>
          <p className="muted" style={{ margin: 0 }}>
            One brief in — specialists plan across Claude, Kimi, ChatGPT, Gemini, Grok, and more
            {offlineDemo ? " (offline demo)." : "."}
          </p>
        </>
      )}

      {noModels && (
        <div className="banner warn">
          No free AI model is currently available.
          <div className="form-row" style={{ marginTop: 8 }}>
            <button type="button" className="px-btn" onClick={onCheckAgain}>
              Check again
            </button>
            <button type="button" className="px-btn primary" onClick={onConfigure}>
              Configure provider
            </button>
          </div>
        </div>
      )}

      {offlineDemo && !noModels && (
        <p className="banner warn">
          Offline demo — responses are simulated. Connect a provider in Settings for live models.
        </p>
      )}

      {freeOnlyBlocked && <p className="banner warn">{freeOnlyBlocked}</p>}

      <form onSubmit={onSubmit} className="task-form" data-testid="command-form">
        <label className="field">
          <span className="visually-hidden">Brief</span>
          <textarea
            className="composer-input"
            data-testid="request-input"
            value={request}
            onChange={(event) => onRequest(event.target.value)}
            rows={compact ? 2 : 4}
            required
            minLength={3}
            placeholder={compact ? "Message Agent Office…" : "Describe your task…"}
            disabled={noModels}
          />
        </label>

        {!compact && (
          <div className="examples">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                className="chip-btn"
                onClick={() => onRequest(example)}
              >
                {example}
              </button>
            ))}
          </div>
        )}

        <div className="form-row">
          <button
            type="submit"
            className="px-btn primary"
            data-testid="assign-work"
            disabled={busy || request.trim().length < 3 || noModels || !!freeOnlyBlocked}
          >
            {busy ? "Starting…" : compact ? "Send" : "Start task"}
          </button>
          <button type="button" className="advanced-toggle" onClick={onToggleAdvanced}>
            {advancedOpen ? "Hide advanced" : "Advanced"}
          </button>
          <span className="meta">Agents: Auto · Models: Auto</span>
        </div>

        {advancedOpen && (
          <div className="advanced-panel">
            <fieldset className="picker">
              <legend>Agents</legend>
              <label className="check">
                <input
                  type="checkbox"
                  data-testid="pick-agents"
                  checked={pickAgents}
                  onChange={(event) => onPickAgents(event.target.checked)}
                />
                Pick agents (otherwise auto-select)
              </label>
              {pickAgents && (
                <div className="picker-grid" style={{ marginTop: 8 }}>
                  {agents.map((agent) => (
                    <label key={agent.id} className="check">
                      <input
                        type="checkbox"
                        data-testid={`agent-${agent.id}`}
                        checked={selectedAgents.includes(agent.id)}
                        onChange={() => onToggleAgent(agent.id)}
                      />
                      {agent.name}
                    </label>
                  ))}
                </div>
              )}
            </fieldset>

            <fieldset className="picker">
              <legend>Routing</legend>
              <div className="mail-tabs" role="radiogroup" aria-label="Routing strategy">
                {(
                  [
                    ["auto", "Auto"],
                    ["one", "One"],
                    ["mixed", "Mixed"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={routingStrategy === value}
                    className={`mail-tab ${routingStrategy === value ? "on" : ""}`}
                    onClick={() => onRoutingStrategy(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {routingStrategy === "one" && (
                <label className="field" style={{ marginTop: 8 }}>
                  <span>Shared model</span>
                  <select
                    value={sharedModel}
                    onChange={(event) => onSharedModel(event.target.value)}
                    required
                  >
                    <option value="">Select a model…</option>
                    {modelOptions.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {routingStrategy === "mixed" && (
                <div className="model-rows" style={{ marginTop: 8 }}>
                  {(pickAgents
                    ? agents.filter((agent) => selectedAgents.includes(agent.id))
                    : agents
                  ).map((agent) => (
                    <label key={agent.id} className="field model-row">
                      <span>{agent.name}</span>
                      <select
                        value={modelOverrides[agent.id] ?? ""}
                        onChange={(event) => onModelOverride(agent.id, event.target.value)}
                      >
                        <option value="">Default</option>
                        {modelOptions.map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                  {roster.length === 0 && <p className="muted">Select agents first.</p>}
                </div>
              )}
            </fieldset>

            <div className="form-row">
              <label className="check">
                <input
                  type="checkbox"
                  checked={requireApproval}
                  onChange={(event) => onRequireApproval(event.target.checked)}
                />
                Pause before code changes
              </label>
              <label className="field compact">
                <span>Budget (USD)</span>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  placeholder="optional"
                  value={maxCost}
                  onChange={(event) => onMaxCost(event.target.value)}
                />
              </label>
            </div>
          </div>
        )}
      </form>
    </section>
  );
}
