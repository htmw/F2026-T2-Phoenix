# Universal Office — Sprint 13: Browser e2e smoke (J-2)

**Status:** Done  
**Goal:** Prove the integrated office path in a real browser — load UI, submit a brief,
reach a terminal workflow status — using Demo Mode (Fake provider) and compose.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U13-1 | `data-testid` hooks on brand, tabs, command form, workflow status | Done |
| U13-2 | Playwright (`@playwright/test`) + Chromium smoke specs | Done |
| U13-3 | `make e2e` / `make e2e-ci` + `npm run test:e2e` | Done |
| U13-4 | CI job: compose up → Playwright → tear down | Done |
| U13-5 | Backlog J-2 Done + architecture / README notes | Done |

## Specs

1. **Office loads** — brand visible; backend badge shows `api ready` or `api degraded`.
2. **Submit-to-result** — Command tab, pick General Agent, Assign work, wait until
   `workflow-status` `data-status="completed"` (Demo Mode / Fake provider; no paid APIs).

## How to run

```bash
# Full cycle (Demo Mode overlay clears provider keys, compose up, test, down):
make e2e-ci

# Against an already-running Demo Mode stack (no live provider API keys):
make up                 # or: docker compose -f docker-compose.yml -f docker-compose.e2e.yml up
cd frontend && npm run test:e2e:install   # once
make e2e
```

Smoke specs require **Demo Mode** (Fake provider). Live provider keys in `.env` will
route to paid APIs and fail the hermetic submit path — use `docker-compose.e2e.yml`.

## Out of scope

- Full J-1 matrix in the browser (API/pytest remains the orchestration suite)
- Multi-browser matrix (Chromium only)
- OAuth / JWT minting in the UI
- Inter-agent permission allow-lists

## Next

Universal Office `NEXT` cadence complete for the committed backlog. Optional follow-ups:
OAuth/OIDC, inter-agent allow-lists, or product polish.
