# Sprint 0 — Universal Multi-Agent AI Office (Discovery)

**Status:** COMPLETE (assessment only — no implementation)  
**Date:** 2026-09-16  
**Scope:** Inspect existing Agent Office; map gaps to Universal Multi-Agent AI Office vision; produce backlog for incremental sprints.  
**Rule followed:** No rewrite. No Sprint 1 code until this assessment is accepted.

This document is the discovery deliverable for transforming the existing Capstone into a
model-agnostic multi-agent collaboration platform. Historical Sprint 0–8 work remains in
`docs/agile/`; this is a **new initiative track**.

---

## CURRENT STATE REPORT

### 1. Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16.3 / React 19 / TypeScript / plain CSS (pixel office theme) |
| Backend | Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy asyncio / Alembic |
| Database | PostgreSQL 17 (durable source of truth) |
| Cache | Redis 8 (provisioned; health-checked; **not yet used as job queue**) |
| Providers | httpx adapters: OpenAI, Anthropic, Google, DeepSeek, xAI, Mistral, OpenRouter + Fake |
| Observability | Prometheus `/metrics` + optional Grafana compose profile |
| Tooling | Ruff, mypy, pytest, ESLint, Make, GitHub Actions CI |

### 2. Frontend architecture

- Single App Router page: `frontend/app/page.tsx` (~855 lines, client component).
- Tabs (in-page state, not routes): **Floor** | **Command** | **Activity**.
- API client: `frontend/lib/api.ts` → `NEXT_PUBLIC_API_BASE_URL`.
- Types: `frontend/lib/types.ts`. Workflow DAG layout: `frontend/lib/graph.ts`.
- No component library, no Settings routes, no frontend test suite.
- Styling: `frontend/app/globals.css` (Press Start 2P / Pixelify / VT323).

### 3. Backend architecture

Modular monolith (`docs/adr/0002`):

```
backend/app/
  api/ routes  ·  agents/  ·  providers/  ·  orchestration/
  workflows/   ·  messaging/ ·  services/ (executor, hive, collaboration, …)
  models/ schemas/ domain/ core/ database/
```

Request path: `POST /api/v1/tasks` → capability analysis → agent selection → DAG plan →
engine (skip / approval / execute / hive / bus handoff) → synthesis.

### 4. Database

Postgres tables (Alembic migrations) for agents, workflows/nodes/executions, messages,
memory, artifacts, presence, network events, providers usage-related records as evolved
through Sprints 1–8. Redis is **ephemeral by ADR** but unused for queues today (bus is
Postgres).

### 5. Agent system

Seven seeded specialists (`backend/app/agents/builtin.py`):

| ID | Role |
|----|------|
| `planning-agent` | Task decomposition |
| `research-agent` | Research / sources |
| `security-agent` | Vulnerability analysis |
| `coding-agent` | Code gen/modify/debug |
| `testing-agent` | Tests |
| `review-agent` | Review / quality |
| `documentation-agent` | Docs / reports |

- Registry is **capability-indexed** (good).
- Agents are data (schemas + DB), not code branches (good).
- **No General agent.** No user-created custom agents API yet (list/get/schema only).
- **Hard pins today:** each builtin sets `preferred_provider` + `preferred_model`
  (e.g. Security → Claude, Research → Gemini, Docs → DeepSeek). Trait routing exists but
  pins win when the preferred model is configured.

### 6. Provider system

- Interface: `LLMProvider` in `backend/app/providers/base.py`.
- Registry: `build_provider_registry(settings)` — only configured keys; else Fake.
- Catalogues are **static tuples** in adapter modules (not live provider model-list APIs).
- No Settings UI to connect/disconnect providers; keys are **env vars only**.
- No encrypted DB credential store; no OAuth/CLI auth; no Ollama/custom endpoint UI.
- No “test connection / refresh models / validate model” product APIs.

### 7. Model system

- Model id form: `provider:external-name` (e.g. `openai:gpt-4o`).
- Traits: reasoning, coding, cheap, fast, structured_output, etc.
- Router: `ProviderRegistry.rank_models` — pin → preferred provider → traits → cost/latency.
- Per-run overrides: `TaskRequest.model_overrides` (works).
- **Missing product modes:** Fixed / Auto / Per-run as first-class agent settings;
  workflow One-model vs Mixed as explicit strategy; provider priority UI; blocked models.
- Fake models in production path when no keys: `fake:reasoner`, `fake:cheap`.

### 8. Workflow system

- DAG engine with sequential/parallel batches, conditional edges, skip-as-success,
  retries, repair feedback loops, human approval gates, cancel/resume.
- Synthesis of final answer (prefers documentation node).
- Strong foundation for Sprint 5 of the new plan; needs wiring for explicit model
  strategies and richer node types (tool task, merge UX).

### 9. Messaging system

- Durable Postgres message bus (ADR 0004).
- Types: task/info request/response, status, artifact reference, error, broadcast,
  approval, discovery, etc.
- Hive loop: drain inbox → optional peer consult (real APIs when keys present) →
  blackboard → speech-act replies.
- Collaboration handoffs write direct agent→agent `task_request`s.
- **Gaps vs vision:** dedicated Inbox/Sent/Archive UX; message types
  `delegation` / `context_request` / `context_response` / `artifact_share` as first-class;
  correlation/idempotency hardening; frontend Message Inspector.

### 10. Memory system

- Visibility: private / shared / workflow (`MemoryService`).
- ContextManager builds a short brief (not full transcript) — aligns with “relevant
  communication” principle.
- **Gaps:** decision log entity, retention controls, richer context packets, permissions
  enforcement beyond visibility enums.

### 11. Artifact system

- `ArtifactStore` stores **references** (URI + metadata), not blobs — correct direction.
- Messages can attach `artifact_ids`.
- **Gaps:** blob storage backend, permissions UI, Artifact browser page, large-file
  pipeline.

### 12. Docker architecture

`docker compose up --build`:

| Service | Role |
|---------|------|
| `postgres` | Healthy-gated volume |
| `redis` | Healthy-gated |
| `backend` | Dev Dockerfile, alembic + uvicorn reload, `/healthz` |
| `frontend` | Dev hot reload; **no healthcheck** |
| `prometheus`/`grafana` | Optional `observability` profile |

Production multi-stage Dockerfiles exist for backend and frontend.

### 13. Existing tests

- **Backend:** ~24 pytest modules (executor, providers, orchestration, engine, hive, bus,
  approval, parallel, metrics, migrations, …). Hermetic FakeProvider; no paid calls.
- **Frontend:** no unit/e2e tests (Sprint 10 J-2 planned).
- CI: lint, typecheck, backend tests, image builds.

### 14. Fake / placeholder model inventory

| ID | Location | Role |
|----|----------|------|
| `fake:reasoner` | `providers/fake.py` | Dev fallback + tests |
| `fake:cheap` | `providers/fake.py` | Dev fallback + tests |
| `fake:lavish` | `tests/test_agent_executor.py` only | Budget tests |
| `FakeProvider` | Auto-registered when **no** real API keys | Local/dev |
| `LiveFakeProvider` / `SlowFakeProvider` | Tests only | Hive / parallel |

No `mock:` / `placeholder:` / `demo:` production IDs. Frontend does not hardcode fakes;
they appear via `GET /api/v1/providers` when Fake is registered.

**Vision conflict:** Fake is presented in the same catalogue as real models (no “Demo Mode”
label). Seeded `preferred_model` pins still show as Default even when only Fake runs.

### 15. Existing technical debt

1. Agent role ≈ model pin in seed data (violates Agent ≠ Model).
2. Static model catalogues (stale IDs/pricing risk).
3. Env-only credentials (no multi-user encrypted connections).
4. Redis unused for queues; runner is request/background session based.
5. No auth (Sprint 9 on old plan) — all control planes public.
6. Monolithic `page.tsx` — Settings/Agents/Workflows pages hard without split.
7. No General agent; no custom agent CRUD.
8. No tool gateway / tool permissions product surface.
9. Message type set incomplete vs vision (delegation, context_request, …).
10. Architecture.md still says Redis queues while bus is Postgres.

### 16. Migration risks

| Risk | Mitigation |
|------|------------|
| Clearing `preferred_model` on seed rewrite | Migration: null bindings + `needs_configuration` when model missing |
| Removing Fake from default registry | Explicit `mock-development` provider + Demo Mode banner; keep for tests |
| Frontend Command Center redesign | Extract components; keep Floor aesthetic (ADR 0006) |
| Provider Settings before Auth | Single-operator encrypted store first; multi-user later |
| Breaking trait routing tests | Keep Fake for tests; never ship fake IDs in “production” catalogue UI |
| Docker volume mounts | New `components/` dir needs compose mount update |

### 17. Proposed target architecture

Preserve modular monolith. Evolve, don’t replace:

```
USER → Command Center → Orchestrator → Workflow Engine
         ↕ Message Bus ↔ Agents (role = specialization, model optional)
         ↕ Context Manager / Memory / Artifacts / Events
         ↕ Model Router → Provider Registry → real adapters
```

Hard rules to enforce incrementally:

- Agent ≠ Model ≠ Provider ≠ Tool
- Any connected compatible model can power any agent
- No fake models in production UI
- Secrets server-side only
- Never silent model substitution
- Maximum **relevant** agent communication (context packets, not dumps)

### 18. Sprint 0 backlog (this discovery) — DONE when

- [x] Repository inspected
- [x] Current state report written
- [x] Fake inventory listed
- [x] Gap map vs Universal Office vision
- [x] Sprint 1 backlog defined
- [x] Stakeholder acceptance to start Sprint 1

### 19. Sprint 1 backlog — Model / Agent decoupling — DONE

| ID | Item | Status |
|----|------|--------|
| U1-1 | Remove hard pins from builtin seeds | Done |
| U1-2 | Optional Fixed binding + `model_strategy` on AgentSummary | Done |
| U1-3 | Migration clears legacy preferred_model/provider JSON | Done |
| U1-4 | FakeProvider Demo Mode; never in production | Done |
| U1-5 | General Agent + `task.general` capability | Done |
| U1-6 | Empty / Demo banners in Command + Settings providers shell | Done |
| U1-7 | Settings → AI Providers read-only catalogue | Done |
| U1-8 | Tests + docs (Agent ≠ Model) | Done |

Exit: no vendor pins on builtins; agents Auto by default; Demo labeled; General agent
seeded; Docker/tests green.

### Sprint 2 — Provider management — DONE

| ID | Item | Status |
|----|------|--------|
| U2-1 | Encrypted `provider_connections` + ENCRYPTION_KEY | Done |
| U2-2 | Connect / test / refresh / disconnect APIs | Done |
| U2-3 | Live `GET /models` discovery (OpenAI-compat + Anthropic) | Done |
| U2-4 | Registry rebuild from Settings keys (env overlay) | Done |
| U2-5 | Settings UI: connect key, status, actions | Done |
| U2-6 | Never echo secrets; masked key hints only | Done |

Next: Sprint 3 — deepen agent communication UX (inbox/sent/archive, message inspector)
or continue routing strategies (Fixed/Auto/One/Mixed) as product surface.

### Sprint 3 — Agent communication — DONE

| ID | Item | Status |
|----|------|--------|
| U3-1 | Context / delegation / artifact_share message types | Done |
| U3-2 | Mailbox API inbox / sent / archive | Done |
| U3-3 | Context packets + fulfill-context | Done |
| U3-4 | Floor mailbox tabs + message inspector | Done |
| U3-5 | Tests + sprint notes | Done |

See `docs/sprints/universal-office-sprint-3.md`.

Next: Sprint 4 — routing strategies (Fixed/Auto/One/Mixed) as product surface.

### Sprint 4 — Routing strategies — DONE

| ID | Item | Status |
|----|------|--------|
| U4-1 | Run strategies Auto / One / Mixed | Done |
| U4-2 | Agent Fixed bindings (Settings + PATCH) | Done |
| U4-3 | Command strategy UI | Done |
| U4-4 | Tests + sprint notes | Done |

See `docs/sprints/universal-office-sprint-4.md`.

Next: Sprint 5 — provider priority / blocked models, or continue office polish.

### Sprint 5 — Provider priority & blocked models — DONE

| ID | Item | Status |
|----|------|--------|
| U5-1 | Routing policy API + table | Done |
| U5-2 | Rank models with priority/blocks | Done |
| U5-3 | Settings UI | Done |
| U5-4 | Tests + docs | Done |

See `docs/sprints/universal-office-sprint-5.md`.

Next: Sprint 6 — office UX polish, artifact browser, or auth prep.

### Sprint 6 — Artifact browser & office polish — DONE

| ID | Item | Status |
|----|------|--------|
| U6-1 | Artifact GET-by-id + created events | Done |
| U6-2 | Floor + Activity artifact browser | Done |
| U6-3 | Tests + docs | Done |

See `docs/sprints/universal-office-sprint-6.md`.

Next: Sprint 7 — auth prep, decision log, or further polish.

### Sprint 7 — Decision log & light retention — DONE

| ID | Item | Status |
|----|------|--------|
| U7-1 | Decision records API + retention purge | Done |
| U7-2 | Approval writers + context packet merge | Done |
| U7-3 | Floor/Activity Decisions UI | Done |
| U7-4 | Tests + docs | Done |

See `docs/sprints/universal-office-sprint-7.md`.

Next: Sprint 8 — auth foundations, or deeper auto-capture of selection/routing decisions.

### 20. Exact files that need changing (Sprint 1 focus)

**Backend (high)**

- `backend/app/agents/builtin.py`
- `backend/app/schemas/agent.py`
- `backend/app/agents/seed.py`
- `backend/app/providers/registry.py` / `fake.py`
- `backend/app/providers/openai_compatible.py`, `anthropic.py` (catalogue exposure)
- `backend/app/api/routes/providers.py`
- New Alembic migration under `backend/migrations/versions/`
- Tests: `test_agents_api.py`, `test_schemas.py`, `test_registry.py`, `test_seed.py`, `test_providers.py`

**Frontend (high)**

- `frontend/app/page.tsx` (model labels, empty states, Command strategy scaffolding)
- `frontend/lib/api.ts`, `frontend/lib/types.ts`
- `frontend/app/globals.css`
- Likely new: `frontend/app/settings/page.tsx` (shell)

**Docs**

- `docs/architecture.md`, `docs/adr/0005-model-routing.md`, `README.md`
- `docs/agile/product-backlog.md` (append Universal Office epics)

**Defer (later sprints)**

- Encrypted provider connections, model discovery APIs, ModelRouter product surface,
  tool gateway, custom agents CRUD, network viz, auth — Sprints 2–9 of new plan.

---

## Gap map (vision vs today)

| Vision area | Today | Gap severity |
|-------------|-------|--------------|
| Agent ≠ Model | Trait router exists; seeds pin vendors | **High** |
| Any model → any agent | Possible via overrides; UX implies fixed pins | **High** |
| Remove fake from prod UI | Fake auto-registers with no keys | **High** |
| Provider Settings + discovery | Env keys only; static catalogues | **High** |
| Secure credential store | Env `SecretStr` only | **High** |
| General + custom agents | Seven specialists only | **Medium** |
| Message bus + hive | Strong foundation | **Low–Medium** (extend types/UX) |
| Workflow DAG | Strong foundation | **Low** (strategies/modes) |
| Context / memory / artifacts | Present, reference-based | **Medium** |
| Model router strategies UI | Backend ranking only | **Medium** |
| Tools + approvals for tools | Approval for workflow nodes only | **High** (new) |
| Auth / multi-user | None | **High** (planned) |
| Activity / office UI | Pixel floor works | **Low** (extend, don’t scrap) |
| Usage / budgets | Metrics exist; budgets partial | **Medium** |

---

## Recommendation

**Do not rewrite.** Treat Universal Office as an epic series on top of the working
Sprints 0–8 platform.

Immediate next step after acceptance: **Sprint 1 (U1-*)** — decouple agents from models,
quarantine Fake to explicit demo/dev, add General agent, empty states, Settings shell.

---

## STOP

Sprint 0 discovery ends here. No Sprint 1 implementation until this assessment is reviewed.
