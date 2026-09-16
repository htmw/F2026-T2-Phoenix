# Sprint 8 Retrospective — Cost, memory, office

**Goal:** answer the five operator questions, give agents scoped memory, and show the
organisation in the UI.

**Delivered:** H-1, H-2, K-2, K-3, K-4, I-3, J-1.

---

## What went well

- Durable answers come from `executions` in Postgres. Prometheus counters are process
  local and advertised as such. Grafana is an optional compose profile so the default
  `docker compose up` stays four services.
- Private memory is a query constraint, not a prompt instruction. A test asserts the
  coding agent's notes do not appear in the security agent's brief.
- The office tab polls `/api/v1/office`, inboxes, and memory without a websocket.

## What went wrong

- Host-side frontend lint still hangs on bind mounts; quality gates for the UI run
  inside the frontend container.

## Decisions worth recording

- Artifacts are references (`uri` + metadata). Blobs are not stored in messages or in
  the artifacts table.
- Production secrets belong in a secrets manager; `.env` is a local convenience. See
  `docs/operations/production.md`.

## Carried forward

- Authentication, workflow ownership, rate limits (Sprint 9).
- Browser-level end-to-end tests (J-2).
- Inter-agent permission allow-lists (still open under I-1).
