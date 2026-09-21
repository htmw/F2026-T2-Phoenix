"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";

export function FinalCTA() {
  const reduce = useReducedMotion();
  return (
    <section className="mkt-section mkt-cta">
      <div className="mkt-grid mkt-section-narrow">
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55 }}
        >
          <p className="mkt-kicker">08 · Begin</p>
          <h2 className="mkt-title">Give your AI team a task.</h2>
          <p className="mkt-body">Open the office, describe the brief, and watch specialists collaborate.</p>
          <Link href="/office" className="mkt-btn mkt-btn-primary mkt-btn-lg">
            Start a task
          </Link>
        </motion.div>
      </div>
    </section>
  );
}

export function MarketingFooter() {
  return (
    <footer className="mkt-footer">
      <div className="mkt-grid mkt-footer-inner">
        <div>
          <strong>AgentMesh</strong>
          <p>An operating system for autonomous AI teams.</p>
        </div>
        <nav aria-label="Footer">
          <a href="#agents">Agents</a>
          <a href="#how-it-works">How it works</a>
          <Link href="/office">Workspace</Link>
        </nav>
      </div>
    </footer>
  );
}
