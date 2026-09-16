# ADR 0007 — Operator identity header + JWT ``sub``

Status: Accepted (amended Sprint 12)  
Date: 2026-09-16

## Context

Approvals, decisions, and workflow control used self-asserted `actor_id` /
`decided_by` strings. There was no ownership on tasks or workflows, so any caller
could list or control any run. Full OAuth/OIDC is out of scope, but we need a durable
ownership key that a JWT `sub` can fill without rewriting history.

## Decision

1. Resolve an **operator identity** from `X-Operator-Id` (office UI / localStorage), or
   from `Authorization: Bearer <JWT>` where the token is **HS256-validated** and
   `sub` is the operator id.
2. Persist that string as `owner_id` on `tasks` and `workflows`.
3. Gate mutating routes on identity; scope workflow list/get/control to the owner.
4. Prefer the resolved identity over body-supplied `decided_by` / `actor_id`.
5. Settings: `AUTH_MODE=header|off`, `DEV_OPERATOR_ID`, `JWT_SECRET` (required in
   production). Optional `JWT_AUDIENCE` / `JWT_ISSUER`.
6. Opaque Bearer strings are **not** accepted — invalid JWTs return 401.

## Consequences

- No password store, refresh tokens, or OAuth providers in this change.
- The UI does not mint JWTs; API clients and gateways do.
- Inter-agent permission allow-lists remain a separate backlog item.
- Browser e2e (J-2) shipped in Universal Office Sprint 13 (Playwright smoke).
