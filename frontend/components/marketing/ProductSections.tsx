"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { WORKFLOW_STEPS } from "@/lib/design/agents";
import { AgentNetwork } from "@/components/marketing/AgentNetwork";

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

export function WorkflowSection() {
  const reduce = useReducedMotion();
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (reduce) {
      return;
    }
    const id = window.setInterval(() => setStep((s) => (s + 1) % WORKFLOW_STEPS.length), 1600);
    return () => window.clearInterval(id);
  }, [reduce]);

  return (
    <section className="mkt-section" id="how-it-works">
      <div className="mkt-grid">
        <Reveal>
          <p className="mkt-kicker">03 · The workflow</p>
          <h2 className="mkt-title">From brief to result.</h2>
        </Reveal>
        <ol className="workflow-rail" aria-label="Workflow stages">
          {WORKFLOW_STEPS.map((label, i) => (
            <li key={label} className={i <= step ? "on" : ""}>
              <button type="button" onClick={() => setStep(i)}>
                <span className="workflow-rail-index">{String(i + 1).padStart(2, "0")}</span>
                <span className="workflow-rail-label">{label}</span>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

export function CommunicationSection() {
  return (
    <section className="mkt-section mkt-section-dark" id="communication">
      <div className="mkt-grid">
        <Reveal>
          <p className="mkt-kicker light">04 · Agents talk to each other</p>
          <h2 className="mkt-title light">AI doesn&apos;t work alone.</h2>
          <p className="mkt-body light mkt-measure">
            One specialist hands findings to the next. A reviewer sends notes back. The loop closes
            when the brief is done. Messages move through the office, quietly, precisely.
          </p>
        </Reveal>
        <Reveal delay={0.1}>
          <AgentNetwork dark className="mkt-comm-viz" />
        </Reveal>
      </div>
    </section>
  );
}

export function WorkspaceSection() {
  const pillars = ["Tasks", "Agents", "Messages", "Artifacts", "Memory", "Workflows"];
  return (
    <section className="mkt-section" id="workspace">
      <div className="mkt-grid">
        <Reveal>
          <p className="mkt-kicker">05 · One workspace</p>
          <h2 className="mkt-title">Everything in one desk.</h2>
          <p className="mkt-body mkt-measure">
            Briefs, specialists, mail, and progress live together, so you watch the organization
            work, not a pile of disconnected chats.
          </p>
        </Reveal>
        <ul className="pillar-list">
          {pillars.map((item, i) => (
            <Reveal key={item} delay={i * 0.04}>
              <li>{item}</li>
            </Reveal>
          ))}
        </ul>
        <Reveal delay={0.08}>
          <div className="product-preview" aria-hidden>
            <div className="product-preview-chrome">
              <span />
              <span />
              <span />
              <em>localhost · Agent Office</em>
            </div>
            <div className="product-preview-body">
              <div className="product-preview-side">
                <strong>Active task</strong>
                <p>Go-to-market plan</p>
              </div>
              <div className="product-preview-agents">
                <div className="pp-row on">
                  <span>Research</span>
                  <em>Working</em>
                </div>
                <div className="pp-row">
                  <span>Analysis</span>
                  <em>Waiting</em>
                </div>
                <div className="pp-row done">
                  <span>Planning</span>
                  <em>Complete</em>
                </div>
                <div className="pp-row">
                  <span>Report</span>
                  <em>Ready</em>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export function ModelsSection() {
  return (
    <section className="mkt-section mkt-section-muted">
      <div className="mkt-grid mkt-two">
        <Reveal>
          <p className="mkt-kicker">06 · AI models</p>
          <h2 className="mkt-title">Agents stay. Models change.</h2>
          <p className="mkt-body">
            A specialist keeps its role whether it runs on Gemini, Groq, Claude, Kimi, or OpenRouter.
            Bring the keys you already subscribe to, the roster does not rename itself after a
            provider.
          </p>
        </Reveal>
        <Reveal delay={0.08}>
          <div className="model-stack" aria-label="Model independence example">
            <div className="model-stack-agent">Specialist</div>
            <div className="model-stack-arrow" aria-hidden />
            <ul>
              <li>Gemini</li>
              <li>Groq</li>
              <li>OpenRouter</li>
              <li>Claude · Kimi · more</li>
            </ul>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export function FreeAISection() {
  return (
    <section className="mkt-section">
      <div className="mkt-grid mkt-section-narrow">
        <Reveal>
          <p className="mkt-kicker">07 · Free AI</p>
          <h2 className="mkt-title">Free AI mode.</h2>
          <p className="mkt-body">
            Prefer verified free or lowest-cost models when you want $0 provider spend. Free Only
            never presents paid models as free, it routes to what your connected catalogue actually
            offers at no (or minimal) cost.
          </p>
          <ul className="free-points">
            <li>Free AI mode</li>
            <li>$0 provider-cost preference</li>
            <li>Verified free models when available</li>
          </ul>
        </Reveal>
      </div>
    </section>
  );
}
