# Sprint Plan

Sprint length: one week. Velocity assumption for the first sprints: ~16 points, to be
recalibrated from actuals after Sprint 2.

Each sprint must leave the system working: tests green, `docker compose up` functional,
docs updated. A sprint is not allowed to end with a half-wired abstraction.

---

## Sprint 0 — Foundation (COMPLETE)

Goal: a repository any engineer can clone, start, and contribute to safely, with a thin
vertical slice proving every container talks to the others.

Committed: A-1 (5), A-2 (3), A-3 (3), A-4 (2), A-5 (3) = **16 points**

Delivered:
- Documentation: architecture, three ADRs, vision, backlog, this plan, Definition of Done.
- Docker development environment: frontend, backend, PostgreSQL, Redis, with health
  gating and hot reload; multi-stage production images for backend and frontend.
- Backend walking skeleton: typed configuration, structured logging, request correlation
  middleware, liveness and readiness endpoints.
- Frontend walking skeleton: page rendering live backend and dependency status.
- Tooling: ruff, mypy, pytest with coverage, ESLint, Makefile, GitHub Actions CI.

Explicitly out of scope: schema, registry, providers, orchestrator, auth.

---

## Sprint 1 — Data foundation and agent registry (COMPLETE)

**COMPLETE.** Ten tables under Alembic, typed contracts with DAG validation, capability-indexed registry, seven agents seeded, agent and capability endpoints. 80 tests.

Goal: agents exist as queryable data with a migrated schema.

Committed: B-1 (5), B-2 (5), C-1 (8), C-2 (3) = 21 points (stretch: C-2)

Key risks: over-modelling the schema. Mitigation: create only the entities the MVP needs;
`workflow_events`, `usage_records`, and `errors` tables wait for the sprints that use them.

Exit criteria: migrations run from empty; seven agents registered and retrievable by
capability; a new agent can be added in a test without touching engine code.

---

## Sprint 2 — Provider abstraction and single-agent execution (COMPLETE)

**COMPLETE.** `LLMProvider` with fake + three OpenAI-compatible catalogues, single-agent execution with validation, timeouts, and cost ceilings. 181 tests.

Goal: one agent produces one validated result through a provider-agnostic interface.

Committed: D-1 (5), D-2 (5), E-1 (8), E-2 (5) = 23 points

Key risks: the provider interface leaking vendor concepts. Mitigation: write the fake
provider and one real adapter against the same test suite before any orchestration
depends on the interface.

Exit criteria: `POST` a task needing one agent, receive a schema-validated result with
recorded tokens, cost, and timing; no test makes a paid API call.

---

## Sprint 3 — Orchestrator and sequential workflows (COMPLETE)

**COMPLETE.** Capability analysis (LLM with heuristic fallback), selection with recorded exclusions, stage-ranked planning, dependency-driven sequential engine, `POST /tasks`. 242 tests.

Goal: the product's core claim — only the required agents run, in dependency order.

Committed: F-1 (13), F-2 (8) = 21 points

Key risks: the capability-analysis step becoming an unvalidated LLM guess. Mitigation:
selection output is schema-validated and every inclusion/exclusion carries a reason.

Exit criteria: a multi-capability request builds a persisted DAG, executes in topological
order, passes structured outputs forward, and excludes irrelevant agents.

---

## Sprint 4 — Parallel workflows (COMPLETE)

**COMPLETE.** Independent agents run concurrently; a join node receives every predecessor; a failed branch keeps sibling results. 260 tests.

Goal: independent agents run concurrently with a working join.

Committed: F-3 (8) + hardening and test debt = ~14 points

Exit criteria: independent agents run concurrently with a working join; measured wall
clock beats the sequential sum; a failing branch does not corrupt siblings.

---

## Sprint 5 — Conditional workflows, retries, cancellation (COMPLETE)

**COMPLETE.** Conditional skips with reasons, per-agent retries, testing→coding feedback
bounded by repair cycles, cancellation and resume from persisted state.

Goal: skip work that is not needed, recover from transient failure, and keep control of a
run that is already in flight.

Committed: F-4 (8), F-5 (8), F-6 (5) = 21 points

Exit criteria: the "security agent finds nothing → coding agent skipped" case passes; the
"testing fails → feedback returns to coding" case passes; workflows cancel and resume.

---

## Sprint 6 — Frontend workflow visualisation (COMPLETE)

**COMPLETE.** Live graph and timeline in the Next.js UI; human approval on code-changing
nodes; synthesised final result; retry/skip/approve/reject from the API and the page.

Goal: a user watches a workflow execute live, including skipped nodes and parallel
branches, and can act on an approval gate.

Committed: G-1 (3), G-2 (13), G-3 (8), F-7 (5), F-8 (5) = 34 points; G-4 pulled forward
because the UI is useless without the controls it renders.

Exit criteria: a user watches a workflow execute live, including skipped nodes and
parallel branches, and can act on an approval gate.

---

## Sprint 7 — Multi-provider support, routing, and the message bus

**COMPLETE.** Anthropic plus OpenAI-compatible catalogues on one conformance suite; ranked
routing with logged reasons and fallback; durable agent mailboxes so agents talk without
the orchestrator copying payloads.

Committed: D-3 (8), D-4 (8) + message bus pulled forward = 16+ points

Exit criteria: three providers pass the shared conformance suite; routing decisions are
logged with reasons; provider failure falls back; a security agent can put a structured
message in the coding agent's inbox.

---

## Sprint 8 — Observability, cost, office UI, memory

**COMPLETE.** Durable metrics API, Prometheus scrape, Grafana dashboard (compose profile),
shared/private/workflow memory, artifact references, office snapshot UI.

Committed: H-1 (8), H-2 (5), I-3 (5), J-1 (8) + network surfaces

Exit criteria: the five operator questions are answerable from the API; Grafana can scrape
`/metrics`; agents have inboxes and scoped memory; production/secrets path is documented.

---

## Sprint 9 — Security, authentication, hardening

Committed: I-1 (8), I-2 (5) = 13 points

Exit criteria: workflows are scoped to their owner; rate limits and budget caps enforced.

---

## Sprint 10 — Testing, performance, documentation

Committed: J-2 (5) remaining; J-1 and I-3 pulled into Sprint 8.

Exit criteria: browser-level submit-to-result coverage; remaining hardening.

---

## Ceremonies

- **Planning** at sprint start: pull from the top of the backlog, confirm acceptance
  criteria, commit to a goal.
- **Review** at sprint end: demonstrate against acceptance criteria; update backlog
  status.
- **Retrospective** at sprint end: recorded in `retrospectives/sprint-N.md`.
- **Backlog refinement** mid-sprint: keep the next sprint's stories `Ready`.
