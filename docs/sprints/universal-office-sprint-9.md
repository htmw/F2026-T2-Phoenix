# Universal Office — Sprint 9: Auth foundations (owners / JWT prep)

**Status:** Done  
**Goal:** Stamp operator identity on workflows and decisions, scope ownership, and
shape the claim slot for a future JWT — without OAuth.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U9-1 | `OperatorIdentity` + `X-Operator-Id` / Bearer resolve | Done |
| U9-2 | `AUTH_MODE` + `DEV_OPERATOR_ID` settings | Done |
| U9-3 | `owner_id` on tasks & workflows (+ migration) | Done |
| U9-4 | Stamp ownership on submit / single-agent run | Done |
| U9-5 | Scope list/get/control to owner | Done |
| U9-6 | Approvals & `POST /decisions` use header identity | Done |
| U9-7 | Protect provider / binding / routing-policy writes | Done |
| U9-8 | Settings + Command operator id (localStorage) | Done |
| U9-9 | ADR 0007 + tests + sprint notes | Done |

## Semantics

- **header mode** — mutating routes 401 without identity
- **off mode** — falls back to `DEV_OPERATOR_ID` (tests / local scripts)
- Opaque Bearer today ≡ operator id; JWT validation replaces that branch later
- System actors (`orchestrator`, `executor`) unchanged for auto-captured decisions

## Out of scope

- OAuth / OIDC / refresh sessions
- Inter-agent permission allow-lists
- Per-user rate limits (I-2)

## Next

Sprint 10 — rate limits / budget caps (I-2). Browser e2e deferred.
