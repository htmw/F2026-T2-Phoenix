"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { OFFICE_AGENTS } from "@/lib/design/agents";

function Reveal({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-10%" }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function IdeaSection() {
  return (
    <section className="mkt-section" id="idea">
      <div className="mkt-grid mkt-section-narrow">
        <Reveal>
          <p className="mkt-kicker">01 · The idea</p>
          <h2 className="mkt-title">
            One AI can work.
            <br />
            An organization of agents can collaborate.
          </h2>
          <p className="mkt-body">
            Agent Mesh is not a chat that fans the same prompt to many models. It is an operating
            system for specialist agents that plan, hand off, and share context until the brief is
            done, whatever the domain.
          </p>
        </Reveal>
      </div>
    </section>
  );
}

export function AgentsSection() {
  return (
    <section className="mkt-section mkt-section-muted" id="agents">
      <div className="mkt-grid">
        <Reveal>
          <p className="mkt-kicker">02 · The agents</p>
          <h2 className="mkt-title">Specialists with clear desks.</h2>
          <p className="mkt-body mkt-measure">
            The office activates only the specialists a brief needs, and when a task calls for a
            discipline the standing desks don&apos;t cover, it designs a bespoke team for that
            request. Models are interchangeable: Gemini, Groq, OpenRouter, and others can power the
            same desk.
          </p>
        </Reveal>
        <div className="agent-roster">
          {OFFICE_AGENTS.map((agent, i) => (
            <Reveal key={agent.id} delay={i * 0.04}>
              <article className="agent-roster-item">
                <h3>{agent.name}</h3>
                <p className="agent-roster-role">{agent.role}</p>
                <p>{agent.blurb}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
