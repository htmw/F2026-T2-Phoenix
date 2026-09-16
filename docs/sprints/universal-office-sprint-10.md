# Universal Office — Sprint 10: Rate limits & soft budget caps

**Status:** Done  
**Goal:** Per-operator abuse protection using Redis counters and Postgres spend
(I-2). Browser e2e (J-2) deferred — no Playwright scaffolding yet.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U10-1 | `AbuseGuard` rate limit (Redis / memory) | Done |
| U10-2 | Soft rolling operator budget from executions | Done |
| U10-3 | Gate mutating routes (429 / 402) | Done |
| U10-4 | `GET /api/v1/me/limits` | Done |
| U10-5 | Settings UI shows remaining rate / budget | Done |
| U10-6 | ADR 0008 + tests + sprint notes | Done |

## Semantics

- Rate: `RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS` per operator
- Budget: `OPERATOR_BUDGET_USD` over `OPERATOR_BUDGET_WINDOW_HOURS` (null = unlimited)
- Health/metrics probes are not rate-limited
- Redis errors fail-open for counters; Postgres remains the spend ledger

## Out of scope

- Playwright / Cypress browser e2e (J-2)
- Hard cancel of in-flight workflows on budget breach
- JWT validation (still ADR 0007 prep only)

## Next

Sprint 11 — production auth-default hardening (J-2 browser e2e remains deferred).
