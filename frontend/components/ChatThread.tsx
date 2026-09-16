"use client";

import type { WorkflowView } from "@/lib/types";
import { formatWhen, shortAgentName } from "@/lib/office";
import { ProviderIcon, providerIdFromModel } from "@/components/ProviderIcon";

function resultText(workflow: WorkflowView): string | null {
  const result = workflow.final_result;
  if (!result || Object.keys(result).length === 0) {
    return null;
  }
  if (typeof result.answer === "string") {
    return result.answer;
  }
  if (typeof result.summary === "string") {
    return result.summary;
  }
  return JSON.stringify(result, null, 2);
}

export function ChatThread({
  workflow,
  busy,
  onOpenWork,
}: {
  workflow: WorkflowView | null;
  busy: boolean;
  onOpenWork: () => void;
}) {
  if (!workflow) {
    return (
      <div className="chat-thread empty">
        <div className="empty-state">
          <div className="empty-orb" aria-hidden />
          <h3>Start a conversation</h3>
          <p>
            Describe a task below. Specialists plan, collaborate across models, and stream the
            answer here.
          </p>
        </div>
      </div>
    );
  }

  const answer = resultText(workflow);
  const live =
    workflow.status === "running" ||
    workflow.status === "pending" ||
    workflow.status === "awaiting_approval";

  return (
    <div className="chat-thread">
      <article className="chat-bubble user">
        <div className="chat-role">You</div>
        <div className="chat-body">{workflow.request}</div>
        <div className="meta">{formatWhen(workflow.created_at)}</div>
      </article>

      {workflow.nodes.map((node) => {
        const last = node.executions.at(-1);
        const nodeAnswer =
          typeof node.result.summary === "string"
            ? node.result.summary
            : typeof node.result.answer === "string"
              ? node.result.answer
              : null;
        return (
          <article className="chat-bubble agent" key={node.key}>
            <div className="chat-role">
              {node.agent_name || shortAgentName(node.agent_id ?? node.key)}
              <span className={`pill ${node.status === "completed" ? "ok" : node.status === "failed" ? "err" : "warn"}`}>
                {node.status.replaceAll("_", " ")}
              </span>
            </div>
            <div className="chat-body">
              {node.status === "failed" && (node.executions.at(-1)?.error_message || workflow.error) && (
                <p className="banner-err" style={{ marginBottom: 8 }}>
                  {last?.error_message || workflow.error}
                </p>
              )}
              {nodeAnswer ||
                (node.status === "running" || node.status === "ready"
                  ? "Working…"
                  : node.status === "waiting"
                    ? "Waiting…"
                    : node.objective.slice(0, 160) + (node.objective.length > 160 ? "…" : ""))}
            </div>
            {last?.model && (
              <div className="meta model-meta">
                {providerIdFromModel(last.model) && (
                  <ProviderIcon providerId={providerIdFromModel(last.model)!} size={14} />
                )}
                {last.model}
                {last.latency_ms ? ` · ${Math.round(last.latency_ms)} ms` : ""}
              </div>
            )}
          </article>
        );
      })}

      {(live || busy) && (
        <article className="chat-bubble agent thinking">
          <div className="chat-role">Office</div>
          <div className="chat-body">
            <span className="status-dot info" aria-hidden /> Agents are working…
          </div>
        </article>
      )}

      {workflow.status === "completed" && answer && (
        <article className="chat-bubble agent result">
          <div className="chat-role">Result</div>
          <pre className="chat-body answer">{answer}</pre>
        </article>
      )}

      {workflow.status === "failed" && workflow.error && workflow.nodes.length === 0 && (
        <article className="chat-bubble agent">
          <div className="chat-role">Office</div>
          <p className="banner-err">{workflow.error}</p>
        </article>
      )}

      <div className="chat-thread-actions">
        <button type="button" className="px-btn ghost" onClick={onOpenWork}>
          View workflow details
        </button>
      </div>
    </div>
  );
}
