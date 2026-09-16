# Sprint 1 — Review and Retrospective

## Sprint goal

Agents exist as queryable data with a migrated schema.

**Outcome: goal met.** 21 of 21 committed points delivered.

## Review

| Story | Points | Status | Evidence |
|-------|--------|--------|----------|
| B-1 Database schema and migrations | 5 | Done | Ten MVP tables under Alembic; upgrade → downgrade → upgrade verified against real PostgreSQL; migration tests run the actual scripts, not `create_all` |
| B-2 Typed domain contracts | 5 | Done | `Task`, `AgentInput`, `AgentOutput`, `AgentResult`, `Workflow`, `WorkflowNode`, `WorkflowEdge`, `EdgeCondition`, `ExecutionError`, `RetryPolicy`, `Approval`, `WorkflowPlan` with DAG validation |
| C-1 Dynamic agent registry | 8 | Done | `AgentRegistry` protocol with in-memory and database implementations; capability lookup is an indexed join; a test registers an unknown agent and selects it with zero engine changes |
| C-2 Seed the seven initial agents | 3 | Done | Seven agents seeded idempotently at startup; `GET /api/v1/agents`, `/agents/{id}`, `/agents/{id}/schema`, `/capabilities` |

80 tests pass, lint and `mypy --strict` clean.

### Demonstrated live

- Startup log: `agents_seeded created=7 total=7`.
- `GET /api/v1/agents` returns all seven with their limits and retry policies.
- `GET /api/v1/agents?capability=security.vulnerability_analysis` returns exactly
  `["security-agent"]` — the exclusion behaviour the product depends on.
- `GET /api/v1/capabilities` shows all 17 capabilities covered, none orphaned.

## Design decisions worth recording

**Capabilities are a table, not a JSON array.** Selection by capability runs on every
submitted task, so it gets an index and a join rather than a scan over JSON.

**`domain/` was added to the documented layout.** Capabilities and statuses are shared
by persistence, API, and orchestration; defining them per layer invites drift.

**Seeding preserves an operator's `enabled` flag.** Startup seeding that silently
re-enabled an agent someone had turned off would be a nasty surprise, so `enabled` is
set on insert only. Capabilities, by contrast, are replaced wholesale: a stale
capability row would keep an agent selectable for work it no longer claims to do.

## What went wrong

**The migration test ran against the development database.** `env.py` resolved the URL
from settings only and ignored the URL passed on the Alembic config, so the test
migrated the dev database — which was already at head — and then asserted against an
empty test database. The assertion failure was real but the cause was the wrong
database, not the wrong schema. Fixed by making `env.py` honour `-x url=...` or a
config-supplied URL ahead of settings, which also makes CI's throwaway database
expressible.

*Lesson: a component that picks its own target silently cannot be tested against a
different one. Make the target injectable.*

**One test asserted something untrue.** The "disabled agent is not selectable" test
asserted an empty result for `testing.execution`, but the enabled `testing-agent`
legitimately provides that capability. The test, not the code, was wrong; it now asserts
the dormant agent's absence rather than an empty list.

*Lesson: when a test fails, confirm the assertion models reality before touching code.*

**Two Alembic conveniences were more trouble than they were worth.** The `ruff` post-write
hook cannot resolve a compiled binary through either `exec` or `console_scripts`, so it
was removed — generated migrations are formatted by `make format` like any other file.
Column types also had to be corrected from JSON objects to JSONB arrays before the
migration left this machine.

## Carry-over

None.

## Next sprint

Sprint 2: the `LLMProvider` interface, a fake provider for tests, one real adapter, and
single-agent execution with output validation, timeouts, and cost ceilings.
