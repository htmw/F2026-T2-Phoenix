# Product Backlog

Ordered by priority. Estimates are story points (Fibonacci). Status is one of
`Done`, `In Sprint`, `Ready`, `Refining`.

Roles: **User** (submits tasks), **Operator** (runs/extends the platform),
**Developer** (builds it).

---

## Epic A — Foundation & Developer Experience

### A-1 Runnable development environment · 5 · Done (Sprint 0)
> As a **Developer**, I want the entire stack to start with one command, so that I can
> contribute without hand-installing databases and runtimes.

Acceptance criteria:
- `docker compose up` starts frontend, backend, PostgreSQL, and Redis.
- Backend waits for PostgreSQL and Redis to be healthy before serving.
- Source edits hot-reload in backend and frontend without an image rebuild.
- Documented in `README.md` with prerequisites and troubleshooting.

### A-2 Configuration and secret handling · 3 · Done (Sprint 0)
> As an **Operator**, I want all configuration supplied by environment variables with
> secrets kept server-side, so that no key is ever hard-coded or exposed to a browser.

Acceptance criteria:
- Typed settings object; invalid configuration fails fast at startup.
- Provider keys held as secret values; they do not appear in logs, errors, or API
  responses.
- `.env.example` documents every variable; `.env` is git-ignored.
- A test asserts secrets are not serialised.

### A-3 Structured logging and request correlation · 3 · Done (Sprint 0)
> As an **Operator**, I want every log line to carry a request ID and structured fields,
> so that I can trace one request through the system.

Acceptance criteria:
- Request ID generated per request, or honoured from an inbound `X-Request-ID`.
- ID bound to the log context and returned in the response header.
- Console rendering in development, JSON in deployed environments.
- Access log records method, path, status, and duration.

### A-4 Health and readiness endpoints · 2 · Done (Sprint 0)
> As an **Operator**, I want liveness and readiness probes, so that orchestrators can tell
> "process alive" from "dependencies reachable".
Acceptance criteria: liveness needs no dependencies; readiness checks PostgreSQL and Redis
and returns a degraded status with per-dependency detail; both covered by tests.

### A-5 Quality gates in CI · 3 · Done (Sprint 0)
> As a **Developer**, I want lint, format, type-check, and tests to run automatically on
> every push, so that broken or unformatted code cannot merge.
Acceptance criteria: CI runs `ruff`, `mypy`, `pytest`, frontend lint and build, and a
compose build; failures block the merge; the same checks are runnable locally via `make`.

---

## Epic B — Data Foundation

### B-1 Database schema and migrations · 5 · Done (Sprint 1)
> As a **Developer**, I want a versioned schema managed by migrations, so that the model
> can evolve safely across environments.
Acceptance criteria: Alembic configured; MVP entities only (`agents`,
`agent_capabilities`, `providers`, `models`, `workflows`, `workflow_nodes`,
`workflow_edges`, `tasks`, `executions`, `agent_results`); upgrade and downgrade both
tested against a real PostgreSQL container; migrations run automatically in development.

### B-2 Typed domain contracts · 5 · Done (Sprint 1)
> As a **Developer**, I want Pydantic schemas for every object agents exchange, so that
> hand-offs are validated rather than assumed.
Acceptance criteria: `Task`, `AgentInput`, `AgentOutput`, `AgentResult`, `Workflow`,
`WorkflowNode`, `WorkflowEdge`, `Execution`, `ExecutionError`, `RetryPolicy`, `Approval`
defined; invalid payloads raise validation errors; round-trip serialisation tested.

---

## Epic C — Agent Registry

### C-1 Dynamic agent registry · 8 · Done (Sprint 1)
> As an **Operator**, I want agents registered as data with declared capabilities, so that
> new agents can be added without modifying the orchestration engine.
Acceptance criteria: agents declare id, name, description, capabilities, input/output
schema, model preference, provider, tools, permissions, timeout, retry policy, cost limit;
registry supports register/lookup/list and query-by-capability; duplicate ids rejected;
a test adds a novel agent and it becomes selectable with zero engine changes.

### C-2 Seed the seven initial agents · 3 · Done (Sprint 1)
> As a **User**, I want planning, research, coding, security, testing, review, and
> documentation agents available, so that realistic requests can be served.
Acceptance criteria: all seven seeded with non-overlapping capability declarations and
persisted; API exposes `GET /agents` with their metadata.

---

## Epic D — Provider Abstraction

### D-1 LLMProvider interface · 5 · Done (Sprint 2)
> As a **Developer**, I want one provider interface, so that no application code calls a
> vendor SDK directly.
Acceptance criteria: interface offers `generate`, `stream`, `estimate_cost`,
`validate_configuration`, `get_model_capabilities`; provider-specific errors are mapped to
a shared error taxonomy; a fake in-memory provider exists for tests.

### D-2 First provider adapter · 5 · Done (Sprint 2)
> As a **User**, I want at least one real provider working, so that agents produce real
> output.
Acceptance criteria: one adapter implemented; token usage and cost captured per call;
timeouts and rate limits handled; tests mock the HTTP layer and make no paid calls.

### D-3 Additional providers · 8 · Done (Sprint 7)
> As an **Operator**, I want at least three providers supported, so that we are not
> dependent on one vendor's availability or pricing.
Acceptance criteria: three adapters passing one shared conformance test suite; missing
keys disable a provider gracefully instead of crashing startup.

### D-4 Model routing · 8 · Done (Sprint 7)
> As an **Operator**, I want each agent routed to an appropriate model, so that reasoning
> work gets strong models and classification gets cheap ones.
Acceptance criteria: routing considers capability, cost, latency, availability, context
size, and user preference; decisions are logged with their reason; fallback on provider
unavailability is tested.

---

## Epic E — Single-Agent Execution

### E-1 Execute one agent end to end · 8 · Done (Sprint 2)
> As a **User**, I want to submit a task that needs one agent and receive a validated
> result, so that the smallest useful path works before orchestration exists.
Acceptance criteria: task persisted; agent invoked via the provider abstraction; output
validated against the agent's output schema; execution record stores status, timing,
tokens, and cost; validation failure is a handled outcome, not a 500.

### E-2 Agent timeouts and cost ceilings · 5 · Done (Sprint 2)
> As an **Operator**, I want per-agent timeouts and cost limits enforced, so that one
> agent cannot hang or overspend.
Acceptance criteria: exceeding the timeout cancels the call and records a timeout error;
exceeding the cost limit prevents the call; both tested.

---

## Epic F — Orchestration

### F-1 Capability analysis and agent selection · 13 · Done (Sprint 3)
> As a **User**, I want the system to select only the agents my request requires, so that
> unnecessary AI calls are avoided.
Acceptance criteria: required capabilities identified from the request; registry queried
by capability; irrelevant agents not activated; selection (including exclusions and the
reason for each) persisted and returned to the client; execution observable.

### F-2 Sequential workflow execution · 8 · Done (Sprint 3)
> As a **User**, I want dependent agents to run in dependency order with each one receiving
> the previous structured output, so that multi-step work composes correctly.
Acceptance criteria: DAG persisted; nodes execute in topological order; each input built
only from declared fields of upstream outputs; state transitions recorded; resumable after
restart.

### F-3 Parallel execution with join · 8 · Done (Sprint 4)
> As a **User**, I want independent agents to run concurrently and their results merged,
> so that workflows are not needlessly slow.
Acceptance criteria: independent nodes run concurrently; a join node receives all upstream
results; wall-clock time is measurably below the sequential sum; one branch failing does
not corrupt the others; concurrency limits respected.

### F-4 Conditional branching · 8 · Done (Sprint 5)
> As a **User**, I want downstream agents skipped when they are not needed, so that (for
> example) no coding agent runs when no vulnerability was found.
Acceptance criteria: edges carry conditions evaluated against upstream structured output;
skipped nodes are recorded as `skipped` with a reason and are visible in the UI; the
security-finds-nothing case is covered by a test.

### F-5 Retry, failure, and escalation · 8 · Done (Sprint 5)
> As a **User**, I want transient failures retried and hard failures surfaced, so that a
> workflow is not lost to one bad response.
Acceptance criteria: per-agent retry policy with backoff; retry count recorded;
non-retryable errors fail fast; exhausted retries either escalate or terminate per policy;
failure feedback can be routed back to an upstream agent (testing → coding).

### F-6 Cancellation and resume · 5 · Done (Sprint 5)
> As a **User**, I want to cancel a running workflow and resume an interrupted one, so
> that I keep control and lose no work.
Acceptance criteria: cancellation stops scheduling and marks in-flight nodes cancelled;
resume restarts from persisted state without re-running completed nodes.

### F-7 Human approval gate · 5 · Done (Sprint 6)
> As a **User**, I want to approve sensitive steps before they run, so that I stay in
> control of consequential actions.
Acceptance criteria: a node can pause awaiting approval; workflow persists across the
wait; approve resumes, reject terminates the branch; approval decision recorded with actor
and timestamp.

### F-8 Result synthesis · 5 · Done (Sprint 6)
> As a **User**, I want one coherent final answer assembled from agent outputs, so that I
> do not read raw fragments.
Acceptance criteria: final result references contributing agents; partial completion is
reported honestly rather than silently omitted.

---

## Epic G — Frontend

### G-1 Task submission · 3 · Done (Sprint 6)
> As a **User**, I want to submit a request and see it accepted, so that I can start work.
Acceptance criteria: input validated; workflow id returned; errors shown clearly.

### G-2 Live workflow visualisation · 13 · Done (Sprint 6)
> As a **User**, I want to see the graph with each agent's live status, so that the
> orchestration behaviour is obvious.
Acceptance criteria: nodes show completed / running / waiting / skipped / failed; parallel
branches shown as parallel; updates arrive without manual refresh; skipped nodes visually
distinct.

### G-3 Timeline, intermediate results, and usage · 8 · Done (Sprint 6)
> As a **User**, I want per-agent timing, intermediate output, model/provider, and
> estimated cost, so that I can understand and trust the run.

### G-4 Retry, skip, and approval controls · 5 · Done (Sprint 6)
> As a **User**, I want to retry a failed agent, skip one, or approve a gate from the UI,
> so that I can steer a workflow without restarting it.

---

## Epic H — Observability & Cost

### H-1 Execution metrics and cost accounting · 8 · Done (Sprint 8)
> As an **Operator**, I want per-workflow cost, duration, token, and retry data, so that I
> can answer what a workflow cost and which agent was slowest.
Acceptance criteria: usage recorded per agent call; aggregate query endpoints exist;
answers exist for cost, slowest agent, retry counts, failing provider, and token totals.

### H-2 Metrics endpoint and dashboards · 5 · Done (Sprint 8)
> As an **Operator**, I want Prometheus-scrapable metrics and a Grafana dashboard, so that
> platform health is visible over time.

---

## Epic I — Security & Hardening

### I-1 Authentication and workflow ownership · 8 · Done (Universal Office Sprint 9)
> As a **User**, I want my workflows private to my account, so that others cannot read my
> tasks or results.
Acceptance: `X-Operator-Id` / Bearer JWT (`sub`); `owner_id` on tasks/workflows; scoped
list/get/control; decision actors from identity. HS256 JWT validation (Sprint 12).

### I-2 Rate limiting and abuse protection · 5 · Done (Universal Office Sprint 10)
> As an **Operator**, I want per-user rate limits and budget caps, so that one account
> cannot exhaust provider quota or spend.
Acceptance: Redis/memory fixed-window rate limits (429); soft rolling spend cap from
executions (402); `GET /me/limits`; ADR 0008.

### I-3 Production deployment path · 5 · Done (Sprint 8)
> As an **Operator**, I want multi-stage production images and secrets-manager support, so
> that deployment does not rely on `.env` files.

---

## Epic J — Quality

### J-1 Workflow test matrix · 8 · Done (Sprint 8)
> As a **Developer**, I want the twelve required workflow scenarios covered by tests, so
> that orchestration regressions are caught.
Covers: single agent; sequential; parallel; conditional branch; agent failure; agent
retry; provider failure; invalid agent output; cancellation; resume; agent skipped; human
approval. All LLM calls mocked.

### J-2 End-to-end tests · 5 · Done (Universal Office Sprint 13)
> As a **Developer**, I want browser-level tests of submit-to-result, so that the
> integrated path is verified.
Acceptance: Playwright Chromium smoke against compose; office loads; Demo Mode
submit reaches `completed`; CI `e2e` job.

### I-4 Production settings fail-fast · 3 · Done (Universal Office Sprint 11)
> As an **Operator**, I want insecure production configuration to refuse startup, so that
> anonymous auth, missing encryption keys, and wildcard CORS cannot ship by accident.
Acceptance: production Settings validators; TrustedHost; narrowed CORS; ADR 0009.

---

## Epic K — Agent network

### K-1 Message bus and mailboxes · 13 · Done (Sprint 7)
> As an **Agent**, I want to send a structured message to another agent without the
> orchestrator copying it, so that collaboration is direct.
Acceptance criteria: typed envelopes persist; inbox/outbox survive restart; unknown
senders are rejected; a workflow hand-off appears as a `task_request` in the recipient
inbox.

### K-2 Shared, private, and workflow memory · 8 · Done (Sprint 8)
> As an **Agent**, I want private notes that other agents cannot read, plus shared
> organisational memory, so that knowledge is scoped.
Acceptance criteria: three visibilities; private rows are invisible to other agents;
context manager injects a short relevant brief, not a transcript.

### K-3 Artifact references · 5 · Done (Sprint 8)
> As an **Agent**, I want to share a file by reference, so that messages stay small.
Acceptance criteria: artifacts store uri/metadata, not blobs; messages may attach ids.

### K-4 Office visualisation · 8 · Done (Sprint 8)
> As a **User**, I want to see agents, inboxes, network links, and activity, so that the
> organisation is visible rather than a single chat window.

