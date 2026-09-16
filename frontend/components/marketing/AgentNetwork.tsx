"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { COMM_EDGES, OFFICE_AGENTS, type OfficeAgentId } from "@/lib/design/agents";

const POSITIONS: Record<OfficeAgentId, { x: number; y: number }> = {
  research: { x: 50, y: 12 },
  planning: { x: 18, y: 38 },
  coding: { x: 50, y: 48 },
  security: { x: 82, y: 38 },
  review: { x: 32, y: 72 },
  testing: { x: 68, y: 72 },
  documentation: { x: 50, y: 90 },
};

type Props = {
  interactive?: boolean;
  dark?: boolean;
  className?: string;
};

export function AgentNetwork({ interactive = true, dark = false, className = "" }: Props) {
  const reduce = useReducedMotion();
  const [active, setActive] = useState<OfficeAgentId>("coding");
  const [pulse, setPulse] = useState(0);
  const [selected, setSelected] = useState<OfficeAgentId | null>(null);

  useEffect(() => {
    if (reduce) {
      return;
    }
    const id = window.setInterval(() => {
      setPulse((n) => n + 1);
      setActive((prev) => {
        const ids = OFFICE_AGENTS.map((a) => a.id);
        const i = ids.indexOf(prev);
        return ids[(i + 1) % ids.length]!;
      });
    }, 2800);
    return () => window.clearInterval(id);
  }, [reduce]);

  const edge = useMemo(() => COMM_EDGES[pulse % COMM_EDGES.length]!, [pulse]);
  const selectedAgent = OFFICE_AGENTS.find((a) => a.id === selected) ?? null;

  return (
    <div className={`agent-network ${dark ? "dark" : ""} ${className}`.trim()}>
      <svg className="agent-network-svg" viewBox="0 0 100 100" role="img" aria-label="Agent collaboration network">
        {COMM_EDGES.map((e) => {
          const a = POSITIONS[e.from];
          const b = POSITIONS[e.to];
          const lit = edge.from === e.from && edge.to === e.to;
          return (
            <line
              key={`${e.from}-${e.to}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              className={`net-edge ${lit ? "lit" : ""}`}
            />
          );
        })}
        {!reduce && (
          <motion.circle
            key={pulse}
            r={0.9}
            className="net-packet"
            initial={{
              cx: POSITIONS[edge.from].x,
              cy: POSITIONS[edge.from].y,
              opacity: 0,
            }}
            animate={{
              cx: POSITIONS[edge.to].x,
              cy: POSITIONS[edge.to].y,
              opacity: [0, 1, 1, 0],
            }}
            transition={{ duration: 1.6, ease: "easeInOut" }}
          />
        )}
      </svg>

      {OFFICE_AGENTS.map((agent) => {
        const pos = POSITIONS[agent.id];
        const isActive = agent.id === active;
        return (
          <button
            key={agent.id}
            type="button"
            className={`net-node ${isActive ? "on" : ""}`}
            style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
            onClick={() => interactive && setSelected(agent.id)}
            disabled={!interactive}
            aria-pressed={selected === agent.id}
          >
            <span className="net-node-dot" aria-hidden />
            <span className="net-node-name">{agent.name}</span>
            {isActive && <span className="net-node-status">Active</span>}
          </button>
        );
      })}

      <p className="net-message" aria-live="polite">
        <strong>{OFFICE_AGENTS.find((a) => a.id === edge.from)?.name}</strong>
        {" → "}
        <strong>{OFFICE_AGENTS.find((a) => a.id === edge.to)?.name}</strong>
        <span>{edge.sample}</span>
      </p>

      {selectedAgent && (
        <aside className="net-detail" aria-label={`${selectedAgent.name} details`}>
          <header>
            <h3>{selectedAgent.name}</h3>
            <button type="button" className="mkt-linkish" onClick={() => setSelected(null)}>
              Close
            </button>
          </header>
          <p className="muted">{selectedAgent.role}</p>
          <p>{selectedAgent.blurb}</p>
          <dl className="net-detail-meta">
            <div>
              <dt>Status</dt>
              <dd>{selectedAgent.id === active ? "Active" : "Ready"}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>Auto</dd>
            </div>
            <div>
              <dt>Current task</dt>
              <dd>{selectedAgent.id === active ? edge.sample : "Waiting for handoff"}</dd>
            </div>
          </dl>
        </aside>
      )}
    </div>
  );
}
