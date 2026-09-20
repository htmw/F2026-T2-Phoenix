"use client";

import type { CSSProperties } from "react";

import type {
  AgentSummary,
  OperatorLimits,
  ProviderStatus,
  RoutingPolicy,
} from "@/lib/types";
import { providerMeta, tierLabel } from "@/lib/providers";
import { ProviderIcon } from "@/components/ProviderIcon";

export function SettingsPanel({
  actor,
  onActor,
  limits,
  providers,
  providerKeys,
  onProviderKey,
  providerBusy,
  providerMessage,
  onProviderAction,
  agents,
  modelOptions,
  bindingBusy,
  onSaveBinding,
  routingPolicy,
  configuredProviderIds,
  catalogueModels,
  policyBusy,
  onSavePolicy,
  advancedOpen,
  onToggleAdvanced,
  freeOnly,
  onToggleFree,
}: {
  actor: string;
  onActor: (value: string) => void;
  limits: OperatorLimits | null;
  providers: ProviderStatus[];
  providerKeys: Record<string, string>;
  onProviderKey: (id: string, value: string) => void;
  providerBusy: string | null;
  providerMessage: string | null;
  onProviderAction: (
    providerId: string,
    action: "connect" | "test" | "refresh" | "disconnect",
  ) => void;
  agents: AgentSummary[];
  modelOptions: { id: string; label: string }[];
  bindingBusy: string | null;
  onSaveBinding: (agentId: string, preferredModel: string | null) => void;
  routingPolicy: RoutingPolicy;
  configuredProviderIds: string[];
  catalogueModels: { id: string; providerLabel: string }[];
  policyBusy: boolean;
  onSavePolicy: (next: RoutingPolicy) => void;
  advancedOpen: boolean;
  onToggleAdvanced: () => void;
  freeOnly: boolean;
  onToggleFree: () => void;
}) {
  const live = providers.filter((p) => !p.demo);
  const demo = providers.filter((p) => p.demo);

  return (
    <div className="settings-stack">
      <section className="panel panel-glow">
        <h2 className="panel-title">General</h2>
        <label className="field">
          <span>Operator ID</span>
          <input
            type="text"
            value={actor}
            maxLength={64}
            onChange={(event) => onActor(event.target.value)}
          />
        </label>
        <label className="check" style={{ marginTop: 12 }}>
          <input type="checkbox" checked={freeOnly} onChange={onToggleFree} />
          Free Only, prefer free/cheapest models when available
        </label>
        <p className="muted" style={{ marginTop: 8 }}>
          Turn Free Only off to use paid subscriptions (Claude, Kimi, ChatGPT, Grok, …) you
          connect below.
        </p>
        {limits && (
          <p className="meta" style={{ marginTop: 12 }}>
            Rate {limits.rate_remaining}/{limits.rate_limit}
            {limits.budget_cap_usd != null
              ? ` · Budget $${limits.budget_spent_usd.toFixed(2)}/$${limits.budget_cap_usd.toFixed(2)}`
              : ""}
          </p>
        )}
      </section>

      <section className="panel panel-glow">
        <div className="panel-head">
          <h2 className="panel-title" style={{ margin: 0 }}>
            AI providers
          </h2>
          <span className="chip accent">Bring your own key</span>
        </div>
        <p className="muted">
          Connect any lab you already subscribe to. Keys stay on the server, never in the browser
          bundle.
        </p>
        {providerMessage && <p className="banner warn">{providerMessage}</p>}
        <div className="provider-showcase">
          {live.map((provider, index) => {
            const meta = providerMeta(provider.name);
            return (
              <article
                key={provider.name}
                className={`provider-card showcase ${provider.configured ? "live" : ""}`}
                style={
                  {
                    "--provider-accent": meta.accent,
                    animationDelay: `${index * 40}ms`,
                  } as CSSProperties
                }
              >
                <div className="provider-mark" aria-hidden>
                  <ProviderIcon providerId={provider.name} size={26} />
                </div>
                <header>
                  <div>
                    <h3>{meta.brand}</h3>
                    <p className="provider-blurb">{meta.blurb}</p>
                  </div>
                  <div className="provider-tags">
                    <span className={`pill ${provider.configured ? "ok" : ""}`}>
                      {provider.configured ? "Connected" : "Not connected"}
                    </span>
                    <span className="pill">{tierLabel(meta.tier)}</span>
                  </div>
                </header>
                <p className="meta">{meta.modelsHint}</p>
                {!provider.configured && (
                  <label className="field">
                    <span>API key</span>
                    <input
                      type="password"
                      autoComplete="off"
                      placeholder={`Paste ${meta.brand} key…`}
                      value={providerKeys[provider.name] ?? ""}
                      onChange={(event) => onProviderKey(provider.name, event.target.value)}
                    />
                  </label>
                )}
                {provider.configured && provider.key_hint && (
                  <p className="meta">Key {provider.key_hint}</p>
                )}
                {provider.models.length > 0 && (
                  <ul className="model-list">
                    {provider.models.slice(0, 6).map((model) => (
                      <li key={model.id}>
                        <span>{model.id}</span>
                        <span>${model.output_cost_per_million}/M</span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="form-row">
                  {!provider.configured ? (
                    <button
                      type="button"
                      className="px-btn primary"
                      disabled={providerBusy === provider.name}
                      onClick={() => onProviderAction(provider.name, "connect")}
                    >
                      Connect
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="px-btn"
                        disabled={providerBusy === provider.name}
                        onClick={() => onProviderAction(provider.name, "test")}
                      >
                        Test
                      </button>
                      <button
                        type="button"
                        className="px-btn"
                        disabled={providerBusy === provider.name}
                        onClick={() => onProviderAction(provider.name, "refresh")}
                      >
                        Refresh models
                      </button>
                      <button
                        type="button"
                        className="px-btn danger"
                        disabled={providerBusy === provider.name}
                        onClick={() => onProviderAction(provider.name, "disconnect")}
                      >
                        Disconnect
                      </button>
                    </>
                  )}
                </div>
              </article>
            );
          })}
          {demo.map((provider) => (
            <article key={provider.name} className="provider-card showcase demo">
              <div className="provider-mark" aria-hidden>
                <ProviderIcon providerId="fake" size={26} />
              </div>
              <header>
                <div>
                  <h3>Offline demo</h3>
                  <p className="provider-blurb">
                    Simulated responses when no live key is connected, for local smoke tests only.
                  </p>
                </div>
                <span className="pill warn">Offline</span>
              </header>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2 className="panel-title">Agents</h2>
        <p className="muted">Optional Fixed model pins. Leave Auto unless you need a specific model.</p>
        <div className="model-rows">
          {agents.map((agent) => (
            <label key={agent.id} className="field model-row">
              <span>{agent.name}</span>
              <select
                value={agent.preferred_model ?? ""}
                disabled={bindingBusy === agent.id}
                onChange={(event) => {
                  const value = event.target.value;
                  onSaveBinding(agent.id, value || null);
                }}
              >
                <option value="">Auto</option>
                {modelOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </section>

      <section className="panel">
        <button type="button" className="advanced-toggle" onClick={onToggleAdvanced}>
          {advancedOpen ? "Hide advanced" : "Advanced"}
        </button>
        {advancedOpen && (
          <div className="advanced-panel" style={{ marginTop: 12 }}>
            <h3 className="panel-title">Routing policy</h3>
            <p className="muted">Provider priority and blocked models.</p>
            <div className="stack-gap">
              {configuredProviderIds.map((id, index) => (
                <div className="row" key={id}>
                  <span className="name provider-priority-name">
                    <ProviderIcon providerId={id} size={18} />
                    {providerMeta(id).brand}
                  </span>
                  <div className="form-row">
                    <button
                      type="button"
                      className="px-btn"
                      disabled={policyBusy || index === 0}
                      onClick={() => {
                        const next = [...configuredProviderIds];
                        const prev = next[index - 1];
                        const cur = next[index];
                        if (prev === undefined || cur === undefined) {
                          return;
                        }
                        next[index - 1] = cur;
                        next[index] = prev;
                        onSavePolicy({ ...routingPolicy, provider_priority: next });
                      }}
                    >
                      Up
                    </button>
                    <button
                      type="button"
                      className="px-btn"
                      disabled={policyBusy || index === configuredProviderIds.length - 1}
                      onClick={() => {
                        const next = [...configuredProviderIds];
                        const cur = next[index];
                        const after = next[index + 1];
                        if (cur === undefined || after === undefined) {
                          return;
                        }
                        next[index] = after;
                        next[index + 1] = cur;
                        onSavePolicy({ ...routingPolicy, provider_priority: next });
                      }}
                    >
                      Down
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <label className="field" style={{ marginTop: 12 }}>
              <span>Blocked models (comma-separated ids)</span>
              <input
                type="text"
                defaultValue={routingPolicy.blocked_models.join(", ")}
                onBlur={(event) => {
                  const blocked = event.target.value
                    .split(",")
                    .map((part) => part.trim())
                    .filter(Boolean);
                  onSavePolicy({ ...routingPolicy, blocked_models: blocked });
                }}
              />
            </label>
            {catalogueModels.length > 0 && (
              <p className="meta" style={{ marginTop: 8 }}>
                Catalogue: {catalogueModels.slice(0, 6).map((m) => m.id).join(", ")}
                {catalogueModels.length > 6 ? "…" : ""}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
