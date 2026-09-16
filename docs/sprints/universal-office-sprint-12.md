# Universal Office — Sprint 12: JWT claim validation

**Status:** Done  
**Goal:** Replace opaque Bearer tokens with HS256 JWT ``sub`` validation (ADR 0007).
Browser e2e (J-2) remains deferred.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U12-1 | `PyJWT` + `JWT_SECRET` / audience / issuer settings | Done |
| U12-2 | Bearer branch decodes HS256 JWT → `sub` | Done |
| U12-3 | Opaque Bearer rejected (401) | Done |
| U12-4 | Production requires `JWT_SECRET` | Done |
| U12-5 | `X-Operator-Id` still preferred for UI | Done |
| U12-6 | Tests + ADR 0007 amend + sprint notes | Done |

## Semantics

- Header wins when both `X-Operator-Id` and Bearer are present
- Missing/invalid/expired JWT → 401 (no opaque fallback)
- `AUTH_MODE=off` without headers still uses `DEV_OPERATOR_ID`

## Out of scope

- OAuth / OIDC / refresh tokens / JWKS
- Frontend JWT minting
- Playwright browser e2e (J-2)

## Next

Sprint 13 — browser e2e smoke (J-2) — **DONE**
(`docs/sprints/universal-office-sprint-13.md`).

Universal Office `NEXT` cadence complete for the committed backlog.
