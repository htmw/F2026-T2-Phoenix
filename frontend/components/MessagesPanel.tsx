"use client";

import type { AgentMailbox, AgentOfficeView } from "@/lib/types";
import { formatWhen, messagePreview, shortAgentName } from "@/lib/office";

type Folder = "inbox" | "sent" | "archive";

export function MessagesPanel({
  agents,
  selected,
  onSelect,
  mailbox,
  folder,
  onFolder,
  showDev,
  onToggleDev,
}: {
  agents: AgentOfficeView[];
  selected: string | null;
  onSelect: (agentId: string) => void;
  mailbox: AgentMailbox | null;
  folder: Folder;
  onFolder: (folder: Folder) => void;
  showDev: boolean;
  onToggleDev: () => void;
}) {
  const messages = mailbox ? mailbox[folder] : [];

  return (
    <div className="message-layout">
      <section className="panel">
        <h2 className="panel-title">Agents</h2>
        {agents.map((item) => (
          <button
            key={item.agent.id}
            type="button"
            className={`agent-list-btn ${selected === item.agent.id ? "on" : ""}`}
            onClick={() => onSelect(item.agent.id)}
          >
            <span>{item.agent.name.replace(/ Agent$/, "")}</span>
            {item.inbox_unread > 0 && <span className="unread">{item.inbox_unread}</span>}
          </button>
        ))}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title" style={{ margin: 0 }}>
            {selected ? shortAgentName(selected) : "Messages"}
          </h2>
          <button type="button" className="advanced-toggle" onClick={onToggleDev}>
            {showDev ? "Hide developer details" : "Developer details"}
          </button>
        </div>

        {!selected && (
          <div className="empty-state">
            <h3>Select an agent</h3>
            <p>Read their inbox and sent mail like a conversation.</p>
          </div>
        )}

        {selected && (
          <>
            <div className="mail-tabs" style={{ marginBottom: 12 }}>
              {(["inbox", "sent", "archive"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`mail-tab ${folder === item ? "on" : ""}`}
                  onClick={() => onFolder(item)}
                >
                  {item}
                </button>
              ))}
            </div>

            {messages.length === 0 && (
              <div className="empty-state">
                <h3>No messages</h3>
                <p>Start a task to see agents collaborate.</p>
              </div>
            )}

            <div className="thread">
              {messages.map((message) => {
                const outbound = message.sender === selected;
                return (
                  <article
                    key={message.id}
                    className={`thread-item ${outbound ? "out" : ""}`}
                  >
                    <div className="who">
                      {shortAgentName(message.sender)}
                      {message.recipient ? ` → ${shortAgentName(message.recipient)}` : ""}
                    </div>
                    <div>{messagePreview(message.content, message.type)}</div>
                    <div className="meta">{formatWhen(message.created_at)}</div>
                    {showDev && (
                      <pre className="details-block" style={{ marginTop: 8 }}>
                        {JSON.stringify(message.content, null, 2)}
                      </pre>
                    )}
                  </article>
                );
              })}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export type { Folder as MailFolderUi };
