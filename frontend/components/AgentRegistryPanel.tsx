"use client";

import { FormEvent, useState } from "react";

import type { AgentEnrollment, AgentSummary } from "@/lib/types";

const DEFAULT_OUTPUT_SCHEMA = JSON.stringify(
  {
    type: "object",
    required: ["summary"],
    properties: {
      summary: { type: "string" },
      score: { type: "number" },
    },
  },
  null,
  2,
);

function capabilityLabel(capability: string): string {
  return capability.replace(".", " · ").replaceAll("_", " ");
}

export function AgentRegistryPanel({
  agents,
  capabilities,
  busyAgent,
  onToggleEnabled,
  onEnroll,
}: {
  agents: AgentSummary[];
  capabilities: string[];
  busyAgent: string | null;
  onToggleEnabled: (agent: AgentSummary) => void;
  onEnroll: (body: AgentEnrollment) => Promise<AgentSummary>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [models, setModels] = useState("");
  const [outputSchema, setOutputSchema] = useState(DEFAULT_OUTPUT_SCHEMA);
  const [maxCost, setMaxCost] = useState("0.5");
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [enrolled, setEnrolled] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const toggleCapability = (capability: string) => {
    setChosen((current) =>
      current.includes(capability)
        ? current.filter((item) => item !== capability)
        : [...current, capability],
    );
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setEnrollError(null);
    setEnrolled(null);
    let schema: Record<string, unknown>;
    try {
      schema = JSON.parse(outputSchema) as Record<string, unknown>;
    } catch {
      setEnrollError("output_schema: not valid JSON.");
      return;
    }
    const cost = Number(maxCost);
    setSubmitting(true);
    try {
      const created = await onEnroll({
        name: name.trim(),
        description: description.trim(),
        capabilities: chosen,
        supported_models: models
          .split(",")
          .map((model) => model.trim())
          .filter(Boolean),
        input_schema: {},
        output_schema: schema,
        cost_profile: { max_cost_usd: Number.isFinite(cost) ? cost : 0.5, timeout_seconds: 120 },
      });
      setEnrolled(`Enrolled ${created.name} (${created.id}).`);
      setName("");
      setDescription("");
      setChosen([]);
      setModels("");
    } catch (cause) {
      setEnrollError(cause instanceof Error ? cause.message : "Enrollment failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <section className="panel" data-testid="agent-registry">
        <h2 className="panel-title">Registry</h2>
        <p className="muted">
          Every enrolled agent, its capabilities and whether the orchestrator may use it.
        </p>
        <div style={{ overflowX: "auto" }}>
          <table className="registry-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Capabilities</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => {
                const status = agent.status ?? (agent.enabled ? "active" : "disabled");
                return (
                  <tr key={agent.id} data-testid={`registry-row-${agent.id}`}>
                    <td>
                      <strong>{agent.name}</strong>
                      <div className="meta">{agent.id}</div>
                    </td>
                    <td data-testid={`registry-capabilities-${agent.id}`}>
                      {agent.capabilities.map((capability) => (
                        <span key={capability} className="chip" data-capability={capability}>
                          {capabilityLabel(capability)}
                        </span>
                      ))}
                    </td>
                    <td>
                      <span
                        className={`pill ${status === "active" ? "ok" : "warn"}`}
                        data-testid={`registry-status-${agent.id}`}
                        data-status={status}
                      >
                        {status}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="px-btn"
                        disabled={busyAgent === agent.id}
                        onClick={() => onToggleEnabled(agent)}
                      >
                        {agent.enabled ? "Disable" : "Enable"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <h2 className="panel-title">Enroll an agent</h2>
        <p className="muted">
          A new agent becomes selectable by capability as soon as it is enrolled, and gets its
          own results table built from its output schema.
        </p>
        <form onSubmit={(event) => void submit(event)} data-testid="enroll-form">
          <label className="field">
            <span>Name</span>
            <input
              data-testid="enroll-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={120}
            />
          </label>
          <label className="field">
            <span>Description</span>
            <input
              data-testid="enroll-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={1000}
            />
          </label>
          <fieldset className="picker">
            <legend>Capabilities</legend>
            <div className="picker-grid">
              {capabilities.map((capability) => (
                <label key={capability} className="check">
                  <input
                    type="checkbox"
                    data-testid={`enroll-capability-${capability}`}
                    checked={chosen.includes(capability)}
                    onChange={() => toggleCapability(capability)}
                  />
                  {capabilityLabel(capability)}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="field">
            <span>Supported models (comma separated, optional)</span>
            <input value={models} onChange={(event) => setModels(event.target.value)} />
          </label>
          <label className="field">
            <span>Output schema (JSON Schema)</span>
            <textarea
              data-testid="enroll-output-schema"
              rows={8}
              value={outputSchema}
              onChange={(event) => setOutputSchema(event.target.value)}
              spellCheck={false}
            />
          </label>
          <label className="field">
            <span>Max cost per run (USD)</span>
            <input
              inputMode="decimal"
              value={maxCost}
              onChange={(event) => setMaxCost(event.target.value)}
            />
          </label>
          {enrollError && (
            <p className="banner-err" role="alert" data-testid="enroll-error">
              {enrollError}
            </p>
          )}
          {enrolled && (
            <p className="banner ok" data-testid="enroll-success">
              {enrolled}
            </p>
          )}
          <div className="form-row">
            <button
              type="submit"
              className="px-btn primary"
              data-testid="enroll-submit"
              disabled={submitting}
            >
              {submitting ? "Enrolling…" : "Enroll agent"}
            </button>
          </div>
        </form>
      </section>
    </>
  );
}
