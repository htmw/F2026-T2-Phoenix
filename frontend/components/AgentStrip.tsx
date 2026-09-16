"use client";

import type { AgentOfficeView, AgentSummary } from "@/lib/types";
import { shortAgentName } from "@/lib/office";

function statusTone(status: string): string {
  if (status === "working" || status === "thinking") {
    return "info";
  }
  if (status === "waiting" || status === "blocked") {
    return "warn";
  }
  if (status === "failed") {
    return "err";
  }
  if (status === "online" || status === "idle") {
    return "ok";
  }
  return "";
}

function modelLabel(agent: AgentSummary): string {
  if (agent.model_strategy === "fixed" && agent.preferred_model) {
    const model = agent.preferred_model.includes(":")
      ? agent.preferred_model.split(":").slice(1).join(":")
      : agent.preferred_model;
    return model;
  }
  return "Auto";
}

export function AgentCard({
  item,
  selected,
  onSelect,
}: {
  item: AgentOfficeView;
  selected: boolean;
  onSelect: () => void;
}) {
  const { agent, presence } = item;
  const task =
    presence.current_task ||
    presence.detail ||
    (presence.status === "idle" ? "Ready" : presence.status);

  return (
    <button
      type="button"
      className={`agent-card ${selected ? "on" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <div className="agent-card-head">
        <p className="agent-card-name">{shortAgentName(agent.id)}</p>
        <span className={`status-dot ${statusTone(presence.status)}`} aria-hidden />
      </div>
      <p className="agent-card-task">{task}</p>
      <p className="agent-card-meta">
        {presence.status.replaceAll("_", " ")}
        {item.inbox_unread > 0 ? ` · ${item.inbox_unread} mail` : ""} · {modelLabel(agent)}
      </p>
    </button>
  );
}

export function AgentStrip({
  agents,
  selected,
  onSelect,
}: {
  agents: AgentOfficeView[];
  selected: string | null;
  onSelect: (agentId: string) => void;
}) {
  if (agents.length === 0) {
    return (
      <div className="empty-state">
        <h3>No agents yet</h3>
        <p>Agents appear here once the office is ready.</p>
      </div>
    );
  }

  return (
    <div className="agent-strip" role="list">
      {agents.map((item) => (
        <div key={item.agent.id} role="listitem">
          <AgentCard
            item={item}
            selected={selected === item.agent.id}
            onSelect={() => onSelect(item.agent.id)}
          />
        </div>
      ))}
    </div>
  );
}
