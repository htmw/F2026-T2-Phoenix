"use client";

import type { NetworkEvent, NetworkLink } from "@/lib/types";
import { formatWhen, shortAgentName } from "@/lib/office";

function eventLabel(event: NetworkEvent): string {
  const type = event.event_type.replaceAll("_", " ");
  const actor = event.actor_id ? shortAgentName(event.actor_id) : "System";
  const title =
    typeof event.payload.title === "string"
      ? ` · ${event.payload.title}`
      : typeof event.payload.summary === "string"
        ? ` · ${event.payload.summary}`
        : "";
  return `${actor}: ${type}${title}`;
}

export function ActivityFeed({
  events,
  links,
  showNetwork,
  onToggleNetwork,
}: {
  events: NetworkEvent[];
  links: NetworkLink[];
  showNetwork: boolean;
  onToggleNetwork: () => void;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title" style={{ margin: 0 }}>
          Activity
        </h2>
        <button type="button" className="advanced-toggle" onClick={onToggleNetwork}>
          {showNetwork ? "Hide network" : "View network"}
        </button>
      </div>

      {events.length === 0 && (
        <div className="empty-state" style={{ padding: "24px 8px" }}>
          <h3>No activity yet</h3>
          <p>Start a task and live updates will appear here.</p>
        </div>
      )}

      <ul className="activity-list">
        {events.slice(0, 12).map((event) => (
          <li key={event.id}>
            <span className="status-dot info" aria-hidden />
            <div>
              <div>{eventLabel(event)}</div>
              <div className="meta">{formatWhen(event.created_at)}</div>
            </div>
          </li>
        ))}
      </ul>

      {showNetwork && (
        <div style={{ marginTop: 16 }}>
          <h3 className="panel-title">Agent links</h3>
          {links.length === 0 && <p className="muted">No collaboration links yet.</p>}
          {links.map((link) => (
            <div className="row" key={`${link.source}-${link.target}-${link.type}`}>
              <span className="name">
                {shortAgentName(link.source)} → {shortAgentName(link.target)}
              </span>
              <span className="muted">
                {link.type} · {link.count}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
