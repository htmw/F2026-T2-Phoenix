"use client";

import { useCallback, useMemo, useState } from "react";

import type { AgentSummary, PlanPreview } from "@/lib/types";

type DraftNode = {
  id: string;
  agentId: string;
};

export function WorkflowBuilder({
  agents,
  busy,
  onPreview,
  onRun,
}: {
  agents: AgentSummary[];
  busy: boolean;
  onPreview: (request: string, agentIds: string[]) => Promise<PlanPreview>;
  onRun: (request: string, agentIds: string[]) => Promise<void>;
}) {
  const [request, setRequest] = useState("");
  const [nodes, setNodes] = useState<DraftNode[]>([]);
  const [dragId, setDragId] = useState<string | null>(null);
  const [preview, setPreview] = useState<PlanPreview | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const roster = useMemo(
    () => agents.filter((agent) => agent.enabled !== false),
    [agents],
  );

  const addAgent = (agentId: string) => {
    if (nodes.some((node) => node.agentId === agentId)) {
      return;
    }
    setNodes((current) => [...current, { id: `${agentId}-${current.length}`, agentId }]);
    setPreview(null);
  };

  const removeNode = (id: string) => {
    setNodes((current) => current.filter((node) => node.id !== id));
    setPreview(null);
  };

  const onDrop = useCallback(
    (targetId: string) => {
      if (!dragId || dragId === targetId) {
        setDragId(null);
        return;
      }
      setNodes((current) => {
        const from = current.findIndex((node) => node.id === dragId);
        const to = current.findIndex((node) => node.id === targetId);
        if (from < 0 || to < 0) {
          return current;
        }
        const next = [...current];
        const moved = next[from];
        if (!moved) {
          return current;
        }
        next.splice(from, 1);
        next.splice(to, 0, moved);
        return next;
      });
      setDragId(null);
      setPreview(null);
    },
    [dragId],
  );

  const agentIds = nodes.map((node) => node.agentId);

  const runPreview = async () => {
    setLocalError(null);
    if (request.trim().length < 3) {
      setLocalError("Describe the task before previewing the plan.");
      return;
    }
    if (agentIds.length === 0) {
      setLocalError("Add at least one agent to the DAG.");
      return;
    }
    setPending(true);
    try {
      setPreview(await onPreview(request.trim(), agentIds));
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : "Plan preview failed");
    } finally {
      setPending(false);
    }
  };

  const runWorkflow = async () => {
    setLocalError(null);
    if (request.trim().length < 3) {
      setLocalError("Describe the task before running.");
      return;
    }
    if (agentIds.length === 0) {
      setLocalError("Add at least one agent to the DAG.");
      return;
    }
    setPending(true);
    try {
      await onRun(request.trim(), agentIds);
      setPreview(null);
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : "Failed to start workflow");
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="panel" data-testid="workflow-builder">
      <div className="panel-head">
        <h2 className="panel-title" style={{ margin: 0 }}>
          Workflow builder
        </h2>
        <p className="meta" style={{ margin: 0 }}>
          Compose a specialist roster, preview the planned DAG, then run it.
        </p>
      </div>

      <label className="field">
        <span>Brief</span>
        <textarea
          data-testid="builder-request"
          rows={3}
          value={request}
          disabled={busy || pending}
          onChange={(event) => setRequest(event.target.value)}
          placeholder="What should this workflow accomplish?"
        />
      </label>

      <div className="builder-layout">
        <div>
          <h3 className="panel-title">Available agents</h3>
          <ul className="builder-palette" data-testid="builder-palette">
            {roster.map((agent) => (
              <li key={agent.id}>
                <button
                  type="button"
                  className="px-btn"
                  disabled={busy || pending || nodes.some((node) => node.agentId === agent.id)}
                  onClick={() => addAgent(agent.id)}
                >
                  {agent.name}
                </button>
                <span className="meta">{agent.capabilities?.slice(0, 3).join(" · ")}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="panel-title">DAG draft (drag to reorder)</h3>
          {nodes.length === 0 ? (
            <p className="muted" data-testid="builder-empty">
              No agents yet. Add specialists from the left.
            </p>
          ) : (
            <ol className="builder-nodes" data-testid="builder-nodes">
              {nodes.map((node, index) => {
                const agent = roster.find((item) => item.id === node.agentId);
                return (
                  <li
                    key={node.id}
                    className={`builder-node${dragId === node.id ? " dragging" : ""}`}
                    draggable
                    onDragStart={() => setDragId(node.id)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() => onDrop(node.id)}
                    data-testid={`builder-node-${node.agentId}`}
                  >
                    <span className="builder-rank">{index + 1}</span>
                    <div>
                      <strong>{agent?.name ?? node.agentId}</strong>
                      <div className="meta">{node.agentId}</div>
                    </div>
                    <button
                      type="button"
                      className="px-btn danger"
                      disabled={busy || pending}
                      onClick={() => removeNode(node.id)}
                    >
                      Remove
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>

      {localError && (
        <p className="banner-err" role="alert">
          {localError}
        </p>
      )}

      <div className="form-row" style={{ marginTop: 12 }}>
        <button
          type="button"
          className="px-btn"
          disabled={busy || pending || !request.trim() || nodes.length === 0}
          onClick={() => void runPreview()}
          data-testid="builder-preview"
        >
          Preview plan
        </button>
        <button
          type="button"
          className="px-btn primary"
          disabled={busy || pending || !request.trim() || nodes.length === 0}
          onClick={() => void runWorkflow()}
          data-testid="builder-run"
        >
          Run workflow
        </button>
      </div>

      {preview && (
        <div className="builder-preview" data-testid="builder-preview-result">
          <h3 className="panel-title">Plan preview</h3>
          <p className="meta">{preview.reasoning}</p>
          <p className="meta">
            Capabilities: {preview.required_capabilities.join(", ") || "none"} · est. max $
            {preview.estimated_max_cost_usd.toFixed(2)}
          </p>
          <ul>
            {preview.nodes.map((node) => (
              <li key={String(node.key)} className="meta">
                <strong>{String(node.agent_name ?? node.agent_id)}</strong>
                {node.objective ? ` — ${String(node.objective).slice(0, 120)}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
