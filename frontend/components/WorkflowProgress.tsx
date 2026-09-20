"use client";

import { useMemo } from "react";

import { rankNodes } from "@/lib/graph";
import type { NodeView, WorkflowStatus, WorkflowView } from "@/lib/types";
import { TERMINAL_STATUSES } from "@/lib/types";

function statusClass(status: string): string {
  if (status === "completed" || status === "succeeded") {
    return "ok";
  }
  if (status === "failed" || status === "cancelled" || status === "blocked") {
    return "err";
  }
  if (status === "skipped") {
    return "warn";
  }
  if (
    status === "running" ||
    status === "ready" ||
    status === "waiting" ||
    status === "awaiting_approval"
  ) {
    return "info";
  }
  return "";
}

function StatusPill({
  status,
  testId,
}: {
  status: WorkflowStatus | NodeView["status"] | string;
  testId?: string;
}) {
  return (
    <span className={`pill ${statusClass(status)}`} data-testid={testId} data-status={status}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function WorkflowProgress({
  workflow,
  busy,
  compact,
  onControl,
  showAdvanced,
  onToggleAdvanced,
}: {
  workflow: WorkflowView;
  busy: boolean;
  compact?: boolean;
  onControl: (action: "approve" | "reject" | "retry" | "skip" | "cancel", nodeKey?: string) => void;
  showAdvanced?: boolean;
  onToggleAdvanced?: () => void;
}) {
  const ranks = useMemo(
    () => rankNodes(workflow.nodes, workflow.edges),
    [workflow.nodes, workflow.edges],
  );
  const ordered = ranks.flat();
  const live = !TERMINAL_STATUSES.has(workflow.status);
  const answer =
    typeof workflow.final_result.answer === "string"
      ? workflow.final_result.answer
      : typeof workflow.final_result.summary === "string"
        ? workflow.final_result.summary
        : null;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title" style={{ margin: 0 }}>
          {compact ? "Current work" : "Workflow"}
        </h2>
        <div className="form-row">
          <StatusPill status={workflow.status} testId="workflow-status" />
          {live && (
            <button
              type="button"
              className="px-btn danger"
              disabled={busy || workflow.cancel_requested}
              onClick={() => onControl("cancel")}
            >
              {workflow.cancel_requested ? "Cancel requested" : "Cancel"}
            </button>
          )}
        </div>
      </div>

      <p className="request">{workflow.request}</p>

      {!compact && (
        <p className="meta">
          {workflow.nodes.length} steps
          {onToggleAdvanced ? (
            <>
              {" · "}
              <button type="button" className="linkish" onClick={onToggleAdvanced}>
                {showAdvanced ? "Hide details" : "Advanced details"}
              </button>
            </>
          ) : null}
        </p>
      )}

      {workflow.error && <p className="banner-err">{workflow.error}</p>}

      <div className="workflow-steps">
        {ordered.map((node) => (
          <div className="workflow-step" key={node.key}>
            <span className={`status-dot ${statusClass(node.status)}`} aria-hidden />
            <div>
              <div className="step-label">{node.agent_name || node.agent_id}</div>
              <div className="step-meta">
                {node.status.replaceAll("_", " ")}
                {!compact && node.objective
                  ? ` · ${node.objective.slice(0, 80)}${node.objective.length > 80 ? "…" : ""}`
                  : ""}
              </div>
              {!compact && (
                <div className="node-actions">
                  {node.status === "awaiting_approval" && (
                    <>
                      <button
                        type="button"
                        className="px-btn primary"
                        disabled={busy}
                        onClick={() => onControl("approve", node.key)}
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className="px-btn danger"
                        disabled={busy}
                        onClick={() => onControl("reject", node.key)}
                      >
                        Reject
                      </button>
                    </>
                  )}
                  {node.status === "failed" && (
                    <>
                      <button
                        type="button"
                        className="px-btn"
                        disabled={busy}
                        onClick={() => onControl("retry", node.key)}
                      >
                        Retry
                      </button>
                      <button
                        type="button"
                        className="px-btn"
                        disabled={busy}
                        onClick={() => onControl("skip", node.key)}
                      >
                        Skip
                      </button>
                    </>
                  )}
                </div>
              )}
              {showAdvanced && node.executions.length > 0 && (
                <pre className="details-block" style={{ marginTop: 8 }}>
                  {JSON.stringify(node.executions.at(-1), null, 2)}
                </pre>
              )}
            </div>
          </div>
        ))}
      </div>

      {workflow.final_result && Object.keys(workflow.final_result).length > 0 && (
        <div style={{ marginTop: 16 }} data-testid="workflow-result">
          <h3 className="panel-title">Result</h3>
          {answer ? (
            <pre className="answer" data-testid="workflow-answer">
              {answer}
            </pre>
          ) : (
            <pre className="answer">{JSON.stringify(workflow.final_result, null, 2)}</pre>
          )}
        </div>
      )}

      {showAdvanced && (
        <pre className="details-block" style={{ marginTop: 12 }}>
          {JSON.stringify(
            {
              id: workflow.id,
              task_id: workflow.task_id,
              total_cost_usd: workflow.total_cost_usd,
              selection: workflow.selection,
            },
            null,
            2,
          )}
        </pre>
      )}
    </section>
  );
}
