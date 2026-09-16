"use client";

import type {
  AgentMailbox,
  AgentMessage,
  AgentOfficeView,
  ArtifactView,
  MemoryView,
} from "@/lib/types";
import { formatWhen, messagePreview, shortAgentName } from "@/lib/office";

export function AgentDrawer({
  item,
  mailbox,
  memory,
  artifacts,
  showAdvanced,
  onToggleAdvanced,
  onClose,
}: {
  item: AgentOfficeView;
  mailbox: AgentMailbox | null;
  memory: MemoryView[];
  artifacts: ArtifactView[];
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
  onClose: () => void;
}) {
  const inbox = mailbox?.inbox ?? [];
  const sent = mailbox?.sent ?? [];
  const recent: AgentMessage[] = [...inbox.slice(0, 5), ...sent.slice(0, 3)].slice(0, 8);

  return (
    <>
      <button type="button" className="drawer-backdrop" aria-label="Close drawer" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={`${item.agent.name} details`}>
        <div className="drawer-header">
          <div>
            <h2 className="panel-title" style={{ margin: 0 }}>
              {item.agent.name}
            </h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>
              {item.presence.status}
              {item.presence.detail ? ` · ${item.presence.detail}` : ""}
            </p>
          </div>
          <button type="button" className="px-btn ghost" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="drawer-body">
          <div className="drawer-section">
            <h3>Current task</h3>
            <p className="muted" style={{ margin: 0 }}>
              {item.presence.current_task || "No active task"}
            </p>
          </div>

          <div className="drawer-section">
            <h3>Model</h3>
            <p className="meta" style={{ margin: 0 }}>
              {item.agent.preferred_model ?? "Auto"} · {item.agent.model_strategy}
            </p>
          </div>

          <div className="drawer-section">
            <h3>Recent messages</h3>
            {recent.length === 0 && <p className="muted">No messages yet.</p>}
            {recent.map((message) => (
              <div className="msg-bubble" key={message.id}>
                <div className="name">
                  {shortAgentName(message.sender)}
                  {message.recipient ? ` → ${shortAgentName(message.recipient)}` : ""}
                </div>
                <div className="body">{messagePreview(message.content, message.type)}</div>
                <div className="meta">{formatWhen(message.created_at)}</div>
              </div>
            ))}
          </div>

          <div className="drawer-section">
            <h3>Artifacts</h3>
            {artifacts.length === 0 && <p className="muted">No artifacts from this desk.</p>}
            {artifacts.slice(0, 6).map((artifact) => (
              <div className="row" key={artifact.id}>
                <span className="name">
                  [{artifact.kind}] {artifact.title}
                </span>
                <span className="muted truncate-uri">{artifact.uri}</span>
              </div>
            ))}
          </div>

          <div className="drawer-section">
            <h3>Memory</h3>
            {memory.length === 0 && <p className="muted">No notes.</p>}
            {memory.slice(0, 6).map((note) => (
              <div className="row" key={note.id}>
                <span className="name">{note.title}</span>
                <span className="muted">{note.visibility}</span>
              </div>
            ))}
          </div>

          <button type="button" className="advanced-toggle" onClick={onToggleAdvanced}>
            {showAdvanced ? "Hide developer details" : "Developer details"}
          </button>
          {showAdvanced && (
            <pre className="details-block">
              {JSON.stringify(
                {
                  agent_id: item.agent.id,
                  capabilities: item.agent.capabilities,
                  presence: item.presence,
                },
                null,
                2,
              )}
            </pre>
          )}
        </div>
      </aside>
    </>
  );
}
