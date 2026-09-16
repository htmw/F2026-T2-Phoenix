# Architecture

Status: living document. Last updated at the end of Sprint 8.

## 1. What this system is

An orchestration engine for specialised AI agents. A user submits one complex request;
the platform decides which agents are required, which are *not* required, how they are
wired into a workflow graph, which model powers each one, and how partial results are
combined into a final answer.

It is explicitly **not** a chat interface that fans the same prompt out to several models.
The product value lives in the routing and control-flow decisions, not in the prompting.

## 2. Architectural style: modular monolith

One deployable backend process containing clear internal module boundaries, plus a
separate frontend, database, and cache.

Rationale: the orchestrator, agent registry, and workflow engine all read and write the
same workflow state within single transactions. Splitting them into services this early
would convert ordinary function calls into distributed transactions and buy us partial
failure, network retries, and deployment coordination with no offsetting benefit. We
start as a monolith and extract a service only when a concrete scaling or isolation
requirement appears. See `adr/0002-modular-monolith.md`.

The one boundary we do expect to cross a process line later is the **agent executor**:
agent runs are long, bursty, and I/O-bound, so they are queued rather than executed
inline. Sprint 0 does not implement the worker, but the queue boundary is where a
separate worker process will be introduced (Sprint 3+).

## 3. Runtime components

| Component  | Technology             | Responsibility |
|------------|------------------------|----------------|
| Frontend   | Next.js (App Router)   | Office (agents, inbox, network, memory), task run, live workflow graph |
| Backend    | Python + FastAPI       | API, orchestrator, registry, message bus, memory, workflow engine, providers |
| Database   | PostgreSQL             | Durable source of truth for workflows, mailboxes, memory, artifacts, events |
| Cache/Queue| Redis                  | Job queues, ephemeral state, caching, rate limits, distributed locks |
| Providers  | External HTTP APIs     | OpenAI (GPT), Anthropic (Claude), Google (Gemini), DeepSeek, xAI, Mistral, OpenRouter |
| Optional   | Prometheus + Grafana   | Compose profile `observability`; scrapes `/metrics` |

Postgres is the source of truth. Redis holds only data we can afford to lose and
rebuild, which keeps workflows resumable after a Redis flush.

## 4. Target backend module layout

Modules are created when a sprint needs them, not upfront. Sprint 0 ships only `core`
and `api`; the rest is the agreed destination so that later work does not re-litigate
structure.

```
backend/app/
  api/            HTTP layer: routers, middleware, dependencies. No business logic.
  core/           Config, logging, health, cross-cutting concerns.
  domain/         Shared vocabulary: capabilities, statuses, error taxonomy.
  schemas/        Pydantic contracts: Task, AgentInput, AgentOutput, Workflow, ...
  models/         SQLAlchemy ORM entities.
  database/       Engine, session management, migration wiring.
  agents/         Agent definitions + registry. Agents are data, not branching code.
  providers/      LLMProvider interface + one adapter per provider. Isolated SDKs.
  messaging/      Message bus, presence, memory, artifacts, context manager.
  orchestration/  Capability analysis, agent selection, workflow construction.
  workflows/      DAG representation and the execution engine.
  services/       Use-case coordination across modules, including collaboration.
  workers/        Background queue consumers.
```

`domain/` exists because capabilities and statuses are referenced by persistence, API,
and orchestration alike; defining them per layer would let the three drift apart.

Dependency direction is inward: `api` → `services`/`orchestration` → `agents`/`providers`
→ `core`. Nothing in `core` imports from the outer layers, and `providers` never imports
`orchestration`.

## 5. Key design commitments

**Agents are registered data, not hard-coded branches.** An agent is a metadata record
(id, capabilities, input/output schema, model preference, tools, permissions, timeout,
retry policy, cost limit). The orchestrator reads the registry; adding an agent must
never require editing the engine.

**Agent ≠ Model ≠ Provider.** Built-in agents declare *traits* (reasoning, coding, …),
not vendor model ids. Any connected compatible model can power any agent. Optional Fixed
bindings and per-run overrides are operator choices; Auto uses the model router. The
development FakeProvider is Demo Mode only and is never registered in production.

**Capability-driven selection.** The orchestrator derives the set of required
*capabilities* from the request, then queries the registry for agents providing them.
Agents whose capabilities are not required are never invoked. "Run everything" is a bug.

**Workflows are DAGs.** Nodes and edges are persisted, so parallel, conditional, and
join topologies are representable from the start rather than retrofitted onto a linear
chain. Sequential execution is simply a DAG with one path.

**Structured, minimal inter-agent payloads.** Agents exchange validated typed objects.
We do not forward whole conversation histories; each agent receives only the fields its
input schema declares. This bounds token cost and makes failures debuggable.

**Validate everything a model produces.** LLM output is untrusted input. It is parsed
against the agent's output schema before it can influence control flow; a validation
failure is a normal, handled outcome (retry / replace / escalate), never a crash.

**Provider independence.** All model calls go through one `LLMProvider` interface
(`generate`, `stream`, `estimate_cost`, `validate_configuration`,
`get_model_capabilities`). Provider-specific request shaping, error mapping, and token
accounting live inside the adapter.

**Secrets stay server-side.** Provider keys are read from the environment by the backend
and/or stored encrypted in ``provider_connections`` when connected through Settings.
API responses expose only masked hints (``••••abcd``), never the secret. No key, and no
value derived from a key, is ever serialised to the frontend. The config layer holds
them as secret types so they cannot be logged accidentally.

## 6. Observability

Every request is assigned a request ID at the middleware boundary and it is bound into
the logging context. Domain logs carry workflow, task, agent, provider, model, latency,
token usage, estimated cost, routing reason, and retry count.

`GET /api/v1/metrics` aggregates durable execution rows (cost, slowest agent, retries,
failing providers, token totals). `GET /metrics` is Prometheus text from process-local
counters. Grafana dashboard JSON is in `observability/grafana/dashboards/`.

Logging is structured (`structlog`): console in development, JSON when deployed.

## 7. Migrations

Alembic owns the schema. The migration URL resolves in this order: an explicit `-x
url=...`, a URL set on the Alembic config by a caller, then application settings — so
"migrate this specific database" is expressible without editing the environment, which
is what lets migration tests and CI run against a throwaway database.

In development, migrations run before the server starts (`Dockerfile.dev`), so a fresh
clone needs one command. In production they are a deliberate deploy step, never
application startup: two replicas booting at once must not race to migrate.

## 8. Request lifecycle (as built)

```
POST /api/v1/tasks
  │
  ├─ CapabilityAnalyser     request text ──> required capabilities (+ reasoning)
  ├─ AgentSelector          capabilities ──> minimal agent set (+ exclusion reasons)
  ├─ WorkflowPlanner        agents ──────> validated DAG
  ├─ WorkflowRepository     plan ────────> persisted task, workflow, nodes, edges
  └─ WorkflowEngine         loop: ready nodes → skip / approval / execute
                              parallel batch; persist after the batch
                              each completed node also sends a task_request on the bus
                              to downstream agents (direct, persisted, inbox-visible)
                              synthesise() builds the final result
```

Direct messages (`POST /api/v1/messages`) never enter this pipeline. Discovery is
`GET /api/v1/discovery?capability=...`.

## 9. Current state (end of Universal Office Sprint 13)

Implemented: Universal Office through operator identity (header + HS256 JWT `sub`),
ownership, abuse limits, production fail-fast settings (ADR 0007–0009), and browser
e2e smoke (J-2 Playwright against compose / Demo Mode).

Deliberately not implemented: OAuth/OIDC and inter-agent permission allow-lists.

Product direction (ADR 0006): an *office of specialists* inspired by multi-agent office
harnesses such as Munder Difflin — inboxes, memory, presence — but implemented as a web
DAG orchestrator over HTTP providers, not an Electron CLI wrapper or pixel floor.
