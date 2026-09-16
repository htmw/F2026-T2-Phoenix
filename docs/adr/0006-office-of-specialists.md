# ADR 0006 — Office of specialists (inspired by, not a clone of, Munder Difflin)

Status: Accepted  
Date: 2026-09-15

## Context

[Munder Difflin](https://github.com/chaitanyagiri/munder-difflin) popularised a clear product
shape: an *office* of collaborating agents with mailboxes, memory, presence, and a human-
facing briefing surface. That metaphor matches what our users need — specialised agents that
talk to each other, not a multi-model chatbot.

Copying that product would be wrong for this capstone: it is an Electron desktop that wraps
terminal coding CLIs (`claude`, `codex`, …) via `node-pty`, coordinates through a local git
"hive" of markdown files, and renders a Pixi.js Animal Crossing–style floor with a
The-Office-inspired cast. Our stack, constraints, and thesis are different.

## Decision

We **borrow the collaboration ideas and the office-floor visual language**, and **reject
the harness/runtime**:

| Keep (inspired) | Leave (theirs, not ours) |
|-----------------|--------------------------|
| Office of named specialists with live presence | Electron + Pixi.js / node-pty CLI wrapping |
| Per-agent inbox / outbox and activity feed | Git repo as the coordination plane |
| Shared + private memory | Markdown-first memory palace + PTY hooks |
| Brief one request; the system assigns work | "Michael" / GOD agent as a terminal persona |
| Chunky SNES-style panels, tiled floor, desk avatars (CSS) | The Office cast sprites and their brand assets |
| Visible who messaged whom (envelope motion) | Copying their codebase |

Our implementation stays a **web modular monolith**: Next.js + FastAPI, Postgres durable
state, Redis ephemeral, capability-driven DAG orchestration, structured
`AgentInput`/`AgentOutput`, and HTTP provider adapters (OpenAI, Anthropic, Gemini,
DeepSeek, …). Agents keep their original names and preferred models
(Security → Claude, Coding → GPT, Research → Gemini, cheap docs → DeepSeek).

## Consequences

- The UI should read as an *office floor + command center*, not a dark SaaS dashboard.
- Product language can say "office", "desk", "inbox", "network" without implying a clone.
- We do not wrap Claude Code / Codex CLIs; agents call HTTP providers through our adapters.
