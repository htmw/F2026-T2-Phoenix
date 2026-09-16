# Universal Office — Sprint 11: Production auth-default hardening

**Status:** Done  
**Goal:** Fail fast on insecure production configuration. Browser e2e (J-2) remains
deferred — Playwright is still greenfield.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U11-1 | Production Settings invariants (`AUTH_MODE`, seed, DEBUG, ENCRYPTION_KEY) | Done |
| U11-2 | Explicit CORS origins + no `*` in production | Done |
| U11-3 | `ALLOWED_HOSTS` + TrustedHostMiddleware in production | Done |
| U11-4 | Narrowed CORS methods/headers in production | Done |
| U11-5 | Ops doc checklist + tests | Done |

## Semantics

- Dev/test may still use `AUTH_MODE=off` and `SEED_AGENTS_ON_STARTUP=true`
- Production misconfig raises `ValidationError` at Settings load (process will not serve)

## Out of scope

- Playwright / Cypress (J-2)
- JWT / OAuth
- Production Compose topology rewrite

## Next

Sprint 12 — JWT claim validation (J-2 browser e2e remains deferred).
