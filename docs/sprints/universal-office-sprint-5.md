# Universal Office — Sprint 5: Provider priority & blocked models

**Status:** Done  
**Goal:** Let operators steer Auto routing with an office-wide provider order and
model blocklist.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U5-1 | `routing_policy` table (singleton) | Done |
| U5-2 | `GET`/`PUT /providers/routing-policy` | Done |
| U5-3 | `rank_models` applies priority + blocks | Done |
| U5-4 | Fixed pins still win over blocks | Done |
| U5-5 | Registry rebuild loads policy on connect/startup | Done |
| U5-6 | Settings: priority Up/Down + block checkboxes | Done |
| U5-7 | Tests + ADR note | Done |

## Semantics

1. **Blocked models** — skipped for Auto/One/Mixed catalogue picks; an agent Fixed pin
   to a blocked id still works.
2. **Provider priority** — earlier vendors sort ahead of later ones (before cost).
3. Unlisted providers sort after every listed one.

## Next

Sprint 6 — artifact browser & office polish — **DONE**
(`docs/sprints/universal-office-sprint-6.md`).

Next: Sprint 7 — auth prep, decision log, or further polish.
