"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";

import { AgentNetwork } from "@/components/marketing/AgentNetwork";

export function HeroSection() {
  const reduce = useReducedMotion();

  return (
    <section className="mkt-hero" id="top">
      <div className="mkt-grid">
        <div className="mkt-hero-copy">
          <motion.p
            className="mkt-eyebrow"
            initial={reduce ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            Agent Office
          </motion.p>
          <motion.h1
            className="mkt-display"
            initial={reduce ? false : { opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.05 }}
          >
            AI agents.
            <br />
            Working together.
          </motion.h1>
          <motion.p
            className="mkt-lede"
            initial={reduce ? false : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.12 }}
          >
            A collaborative AI workspace where autonomous agents research, plan, build, review, and
            test as one organization.
          </motion.p>
          <motion.div
            className="mkt-hero-cta"
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.18 }}
          >
            <Link href="/office" className="mkt-btn mkt-btn-primary mkt-btn-lg">
              Start a task
            </Link>
            <a href="#agents" className="mkt-btn mkt-btn-ghost mkt-btn-lg">
              Explore agents
            </a>
          </motion.div>
        </div>
        <motion.div
          className="mkt-hero-visual"
          initial={reduce ? false : { opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7, delay: 0.15 }}
        >
          <AgentNetwork />
        </motion.div>
      </div>
    </section>
  );
}
