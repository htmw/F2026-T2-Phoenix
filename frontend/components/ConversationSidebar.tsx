"use client";

import type { WorkflowStatus, WorkflowView } from "@/lib/types";
import { formatWhen } from "@/lib/office";

function titleFrom(workflow: WorkflowView): string {
  const text = workflow.request.trim().replace(/\s+/g, " ");
  if (text.length <= 48) {
    return text || "Untitled";
  }
  return `${text.slice(0, 48)}…`;
}

function statusTone(status: WorkflowStatus): string {
  if (status === "completed") {
    return "ok";
  }
  if (status === "failed" || status === "cancelled") {
    return "err";
  }
  if (status === "running" || status === "awaiting_approval" || status === "pending") {
    return "info";
  }
  return "";
}

export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
}: {
  conversations: WorkflowView[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <aside className="chat-sidebar panel" aria-label="Conversations">
      <button type="button" className="px-btn primary chat-new" onClick={onNew}>
        New chat
      </button>
      <h2 className="chat-sidebar-label">Chats</h2>
      {conversations.length === 0 && (
        <p className="muted" style={{ padding: "0 4px", margin: 0 }}>
          Your conversations will show up here.
        </p>
      )}
      <ul className="chat-history">
        {conversations.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className={`chat-history-item ${activeId === item.id ? "on" : ""}`}
              onClick={() => onSelect(item.id)}
            >
              <span className="chat-history-title">{titleFrom(item)}</span>
              <span className="chat-history-meta">
                <span className={`status-dot ${statusTone(item.status)}`} aria-hidden />
                {item.status.replaceAll("_", " ")} · {formatWhen(item.created_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
