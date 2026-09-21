"use client";

import type { WorkflowView } from "@/lib/types";
import { formatWhen, shortAgentName } from "@/lib/office";
import { BrandLogo } from "@/components/BrandLogo";
import { ProviderIcon, providerIdFromModel } from "@/components/ProviderIcon";
import { BRAND_NAME } from "@/lib/brand";

function resultText(workflow: WorkflowView): string | null {
  const result = workflow.final_result;
  const fromNodes = workflow.nodes
    .map((node) => nodeBody(node.result))
    .filter((text): text is string => Boolean(text && text.trim()));

  const richestNode = fromNodes.reduce<string | null>((best, text) => {
    if (!best || text.length > best.length) {
      return text;
    }
    return best;
  }, null);

  if (result && Object.keys(result).length > 0) {
    if (typeof result.answer === "string" && result.answer.trim()) {
      const answer = result.answer.trim();
      // Prefer a fuller node deliverable when synthesis only kept a short summary label.
      if (richestNode && richestNode.length > answer.length + 40) {
        return richestNode;
      }
      return answer;
    }
    if (typeof result.summary === "string" && result.summary.trim()) {
      return richestNode && richestNode.length > result.summary.length
        ? richestNode
        : result.summary;
    }
  }

  if (richestNode) {
    return richestNode;
  }
  if (result && Object.keys(result).length > 0) {
    return JSON.stringify(result, null, 2);
  }
  return null;
}

function nodeBody(result: Record<string, unknown>): string | null {
  for (const key of ["answer", "document", "content", "code"] as const) {
    const value = result[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }

  const changes = result.changes;
  if (Array.isArray(changes) && changes.length > 0) {
    const blocks: string[] = [];
    for (const raw of changes) {
      if (!raw || typeof raw !== "object") {
        continue;
      }
      const change = raw as Record<string, unknown>;
      const file = String(change.file ?? "file");
      const content = typeof change.content === "string" ? change.content : null;
      const diff = typeof change.diff === "string" ? change.diff : null;
      if (content?.trim()) {
        blocks.push(`### ${file}\n\n\`\`\`\n${content.trimEnd()}\n\`\`\``);
      } else if (diff?.trim()) {
        blocks.push(`### ${file}\n\n\`\`\`diff\n${diff.trimEnd()}\n\`\`\``);
      }
    }
    if (blocks.length > 0) {
      const summary = typeof result.summary === "string" ? result.summary.trim() : "";
      return summary ? `${summary}\n\n${blocks.join("\n\n")}` : blocks.join("\n\n");
    }
  }

  const artifacts = result.artifacts;
  if (Array.isArray(artifacts) && artifacts.length > 0) {
    const blocks: string[] = [];
    for (const raw of artifacts) {
      if (!raw || typeof raw !== "object") {
        continue;
      }
      const artifact = raw as Record<string, unknown>;
      const name = String(artifact.name ?? "artifact");
      const content = typeof artifact.content === "string" ? artifact.content : null;
      if (content?.trim()) {
        blocks.push(`### ${name}\n\n\`\`\`\n${content.trimEnd()}\n\`\`\``);
      }
    }
    if (blocks.length > 0) {
      const summary = typeof result.summary === "string" ? result.summary.trim() : "";
      return summary ? `${summary}\n\n${blocks.join("\n\n")}` : blocks.join("\n\n");
    }
  }

  if (typeof result.summary === "string" && result.summary.trim()) {
    return result.summary;
  }
  return null;
}

function TurnView({
  turn,
  active,
  busy,
}: {
  turn: WorkflowView;
  active: boolean;
  busy: boolean;
}) {
  const answer = resultText(turn);
  const live =
    turn.status === "running" ||
    turn.status === "pending" ||
    turn.status === "awaiting_approval";

  return (
    <>
      <article className="chat-bubble user">
        <div className="chat-role">You</div>
        <div className="chat-body">{turn.request}</div>
        <div className="meta">{formatWhen(turn.created_at)}</div>
      </article>

      {turn.nodes.map((node) => {
        const last = node.executions.at(-1);
        const nodeAnswer = nodeBody(node.result);
        return (
          <article className="chat-bubble agent" key={node.key}>
            <div className="chat-role">
              {node.agent_name || shortAgentName(node.agent_id ?? node.key)}
              <span className={`pill ${node.status === "completed" ? "ok" : node.status === "failed" ? "err" : "warn"}`}>
                {node.status.replaceAll("_", " ")}
              </span>
            </div>
            <div className="chat-body">
              {node.status === "failed" && (node.executions.at(-1)?.error_message || turn.error) && (
                <p className="banner-err" style={{ marginBottom: 8 }}>
                  {last?.error_message || turn.error}
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

      {active && (live || busy) && (
        <article className="chat-bubble agent thinking">
          <div className="chat-role">AgentMesh</div>
          <div className="chat-body">
            <span className="status-dot info" aria-hidden /> Agents are working…
          </div>
        </article>
      )}

      {turn.status === "completed" && answer && (
        <article className="chat-bubble agent result">
          <div className="chat-role">Result</div>
          <pre className="chat-body answer">{answer}</pre>
        </article>
      )}

      {turn.status === "failed" && turn.error && turn.nodes.length === 0 && (
        <article className="chat-bubble agent">
          <div className="chat-role">AgentMesh</div>
          <p className="banner-err">{turn.error}</p>
        </article>
      )}
    </>
  );
}

export function ChatThread({
  workflow,
  history = [],
  busy,
  onOpenWork,
}: {
  workflow: WorkflowView | null;
  history?: WorkflowView[];
  busy: boolean;
  onOpenWork: () => void;
}) {
  if (!workflow && history.length === 0) {
    return (
      <div className="chat-thread empty">
        <div className="empty-state">
          {busy ? (
            <div className="empty-orb loading" aria-hidden />
          ) : (
            <BrandLogo size={64} variant="mark" className="empty-brand-logo" />
          )}
          <h3>{busy ? "Starting…" : "Start a conversation"}</h3>
          <p>
            {busy
              ? "Assigning specialists and opening the thread."
              : `Describe a task below. ${BRAND_NAME} specialists plan, collaborate across models, and stream the answer here.`}
          </p>
        </div>
      </div>
    );
  }

  // Prior turns first, then the active one. Each turn keeps its own request and result,
  // so a follow-up reads as a continuation rather than a fresh thread.
  const turns = [...history, ...(workflow ? [workflow] : [])];
  const activeId = workflow?.id ?? null;

  return (
    <div className="chat-thread">
      {turns.map((turn) => (
        <TurnView key={turn.id} turn={turn} active={turn.id === activeId} busy={busy} />
      ))}

      <div className="chat-thread-actions">
        <button type="button" className="px-btn ghost" onClick={onOpenWork}>
          View workflow details
        </button>
      </div>
    </div>
  );
}
