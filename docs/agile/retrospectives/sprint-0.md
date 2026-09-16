# Sprint 0 — Review and Retrospective

## Sprint goal

A repository any engineer can clone, start, and contribute to safely, with a thin
vertical slice proving every container talks to the others.

**Outcome: goal met.** 16 of 16 committed points delivered.

## Review — delivered against acceptance criteria

| Story | Points | Status | Evidence |
|-------|--------|--------|----------|
| A-1 Runnable development environment | 5 | Done | `docker compose up` starts four services; backend gated on Postgres and Redis health; hot reload verified by editing a mounted file and re-fetching the page |
| A-2 Configuration and secret handling | 3 | Done | Typed `Settings`; keys held as `SecretStr`; tests assert keys survive neither `str`, `repr`, nor JSON serialisation; `.env` untracked and CI-enforced |
| A-3 Structured logging and request correlation | 3 | Done | structlog pipeline, console/JSON rendering, `X-Request-ID` honoured and returned, id bound into the log context, access log with method/path/status/duration |
| A-4 Health and readiness endpoints | 2 | Done | `/healthz` touches no dependency; `/readyz` checks Postgres and Redis concurrently and returns 503 when degraded, verified live as `ready` |
| A-5 Quality gates | 3 | Done | `make check` = ruff + mypy --strict + pytest + eslint + tsc; CI workflow adds dev/prod image builds and a secret scan |

23 backend tests pass; lint and strict type-check clean; 98% statement coverage.

### Demonstrated live

- `GET /readyz` → `ready`, with Postgres at 31 ms and Redis at 20 ms over the compose
  network.
- Frontend at `localhost:3000` renders backend `ready` and both dependencies `healthy`.
- `docker compose run --rm --no-deps backend pytest` → 23 passed inside the container.

## What went well

- Documenting decisions before coding kept Sprint 0 genuinely small. The temptation was
  to scaffold `agents/`, `providers/`, and `orchestration/` as empty packages; writing
  the target layout into `architecture.md` instead gave the same clarity with no dead
  code.
- The walking skeleton earned its place immediately — it exposed two defects (below) that
  no amount of unit testing would have surfaced.

## What went wrong

**A config bug reached Docker that unit tests could not see.** `pydantic-settings`
JSON-decodes complex fields directly from the environment *before* field validators run,
so `CORS_ALLOW_ORIGINS=http://localhost:3000` crash-looped the backend. The existing test
passed the same value to the constructor, which takes a different code path, and so
passed happily. Fixed with `NoDecode`; regression tests now load settings through the
environment source.

*Lesson: when configuration has two entry paths, test the one production uses.*

**Next.js dev died on the macOS bind mount.** Next takes a file lock on
`next-env.d.ts`; file locking is unsupported on macOS bind mounts, so the dev server
failed with `EDEADLK`, surfaced as the unhelpful `Unknown system error -35`. Diagnosis
was slowed by an earlier transient `EIO` on the same mount that looked like the same
fault but was not. Fixed by mounting only edited source directories and keeping
generated files on the container filesystem.

*Lesson: a generic I/O error on a bind mount deserves errno translation before a
hypothesis.*

**Three dependency pins had to be corrected.** `pytest-cov 8.0.0` does not exist;
ESLint 10 breaks plugins bundled in `eslint-config-next`; TypeScript 7 is unsupported by
`typescript-eslint`. Latest-available is not the same as compatible.

*Lesson: verify a pin against the toolchain that must consume it, not against the
registry's newest tag.*

## What we will change next sprint

1. Add a smoke check that hits `/readyz` against the running stack, so integration-level
   breakage is caught by a command rather than by manual inspection.
2. When Sprint 1 introduces the database, write migration tests against a real
   PostgreSQL container from the outset — a migration that only works against SQLite
   would be the same class of defect as the config bug above.
3. Keep dependency bumps separate from feature work so a compatibility break is easy to
   isolate.

## Deliberately deferred

No database schema, agent registry, provider adapter, orchestrator, workflow engine, or
authentication. All are scheduled in the sprint plan and none was started, which is the
intended Sprint 0 outcome.

## Carry-over

None.

## Note on version control

This sprint's work is present in the working tree but **not committed**. Version control
is owned by the team: branching strategy, commit granularity, and history are group
decisions. The conventions proposed in `README.md` (`main` / `develop` / `feature/*`,
Conventional Commits) are a suggestion for the team to accept or replace.
