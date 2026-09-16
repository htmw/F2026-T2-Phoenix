# ADR 0002: Start as a modular monolith

- Status: Accepted
- Date: Sprint 0

## Context

The target architecture names several components — orchestrator, agent registry, model
router, workflow engine, agent executor, provider layer. Naming them as boxes invites
deploying them as separate services. We have to decide the deployment topology now
because it determines how modules communicate.

These components are highly coupled around one piece of state: the workflow. Selecting
agents, writing the workflow graph, and recording execution results are steps in a
single logical operation that should either all commit or all roll back.

## Decision

Build one backend deployable with enforced internal module boundaries. Components
communicate by function call and share a single database. A background worker consuming
a Redis queue is the only additional process we anticipate, because agent execution is
long-running and must not block request handling.

Module boundaries are maintained by dependency direction (`api` → `services` →
`agents`/`providers` → `core`) rather than by network hops.

## Consequences

- Workflow construction can be transactional; no distributed saga needed for the MVP.
- Local development needs four containers, not a dozen; `docker compose up` stays usable.
- We accept that scaling is coarse-grained: the whole backend scales together. This is
  acceptable because the load is I/O-bound on provider APIs, and the executor — the part
  that would actually need independent scaling — is already behind a queue boundary and
  can be extracted without touching callers.
- If a provider adapter or the executor later needs isolation (e.g. untrusted tool
  execution), extraction is a deployment change at an existing seam, not a rewrite.
