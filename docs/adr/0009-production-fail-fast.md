# ADR 0009 — Production settings fail-fast

Status: Accepted  
Date: 2026-09-16

## Context

Defaults that are convenient locally (`AUTH_MODE=off`, seed-on-startup, missing
`ENCRYPTION_KEY`, open CORS) are dangerous if they silently carry into production.
Sprint 9–10 added identity and rate limits, but production still accepted insecure
combinations.

## Decision

When `ENVIRONMENT=production`, Settings validation requires:

- `AUTH_MODE=header`
- `DEBUG=false`
- `SEED_AGENTS_ON_STARTUP=false`
- non-empty `ENCRYPTION_KEY`
- explicit non-wildcard `CORS_ALLOW_ORIGINS` and `ALLOWED_HOSTS`

`TrustedHostMiddleware` and a narrowed CORS method/header list apply only in production.

## Consequences

- Misconfigured production deploys fail at boot instead of serving anonymously.
- Local/dev/test paths are unchanged.
- Browser e2e (J-2) shipped in Universal Office Sprint 13 (Playwright smoke).
