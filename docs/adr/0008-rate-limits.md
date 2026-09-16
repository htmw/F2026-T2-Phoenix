# ADR 0008 — Per-operator rate limits and soft budget caps

Status: Accepted  
Date: 2026-09-16

## Context

Sprint 9 stamped `owner_id` on workflows. Without request and spend caps, one operator
can still flood mutating routes or burn provider quota. Redis is already required for
readiness (ADR 0003) and was unused for application logic.

## Decision

1. **Rate limit** — fixed-window counter per operator id (`agentorch:rl:{id}` in Redis,
   or an in-process map when `RATE_LIMIT_BACKEND=memory`). Mutating routes return **429**
   with `Retry-After`.
2. **Soft budget** — rolling-window sum of `executions.cost_usd` for workflows owned by
   the operator (Postgres is the ledger). New submits return **402** when the cap is hit;
   in-flight runs are not killed.
3. Redis outages **fail-open** for rate counting so a cache blip does not brick the API;
   `/readyz` still reports Redis health separately.
4. Expose `GET /api/v1/me/limits` for the Settings UI.

## Consequences

- Abuse protection is keyed by the same string as ownership / future JWT `sub`.
- Browser e2e (J-2) shipped in Universal Office Sprint 13; this ADR does not add Playwright.
