# Universal Office — Sprint 7: Decision log & light retention

**Status:** Done  
**Goal:** Promote office decisions from a memory-tag convention to a first-class log
with optional expiry. Auth remains Sprint 9.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U7-1 | `decision_records` table + `DecisionKind` | Done |
| U7-2 | `POST/GET /decisions`, `GET /decisions/{id}` | Done |
| U7-3 | `POST /decisions/purge-expired` retention | Done |
| U7-4 | Approvals auto-record decisions | Done |
| U7-5 | Context packets merge decision log | Done |
| U7-6 | Floor + Activity Decisions panels | Done |
| U7-7 | Tests + sprint notes | Done |

## Semantics

- Decisions are self-asserted (`actor_id`) until auth lands
- `expires_at` null = keep forever; purge removes only expired rows
- List endpoints hide expired entries unless `include_expired=true`

## Next

Sprint 8 — auto-capture of selection/routing decisions into the log (auth stays Sprint 9).
