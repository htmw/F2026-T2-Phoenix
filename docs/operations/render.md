# Deploying to Render

Agent Mesh deploys to [Render](https://render.com) as a Blueprint. One click provisions
four resources from [`render.yaml`](../../render.yaml):

| Resource | Render type | Purpose |
|----------|-------------|---------|
| `agent-mesh-db` | PostgreSQL | durable state (workflows, agents, memory, …) |
| `agent-mesh-redis` | Key Value | rate limits, cache, locks |
| `agent-mesh-api` | Web (Docker) | FastAPI backend |
| `agent-mesh-web` | Web (Docker) | Next.js frontend |

## One-click deploy

1. Make sure `render.yaml` is committed at the repo root (it is).
2. In the README, click **Deploy to Render** — or, in the Render dashboard:
   **New → Blueprint → select this repo → Apply**.
3. Render builds both images, runs database migrations on the API's first boot, seeds the
   built-in agents, and starts everything. First build takes a few minutes.

The app comes up in **demo mode**: with no provider key set, a built-in fake provider
returns simulated responses so the whole pipeline works end-to-end.

## Going live with real AI

On the **`agent-mesh-api`** service → **Environment**, set `OPENAI_API_KEY` (and/or any of
`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, etc.), then **Manual Deploy → Deploy latest commit**.
The office then routes to real models. Keys are read only by the backend and never sent to
the browser.

## How it is wired

- **Database URL** is injected from the managed Postgres. The backend rewrites a
  `postgres(ql)://` URL to the `postgresql+asyncpg://` driver and drops a libpq-only
  `sslmode` param automatically (see `Settings._normalise_database_url`).
- **Migrations** run on container start (`alembic upgrade head && uvicorn …`), so no paid
  pre-deploy step is needed. Migrations are idempotent and safe on a single instance.
- **Port**: Render assigns `$PORT`; the API's start command binds uvicorn to it.
- **Frontend API base**: `NEXT_PUBLIC_API_BASE_URL` is a build argument because Next.js
  inlines `NEXT_PUBLIC_*` into the client bundle at build time.
- **CORS**: the backend allows the frontend's Render URL; both default to the service
  names in `render.yaml`.

## Environment reference (set in `render.yaml` unless noted)

| Variable | Value | Notes |
|----------|-------|-------|
| `ENVIRONMENT` | `staging` | not `production`, so docs stay on and agents seed on boot |
| `AUTH_MODE` | `header` | app works with the default operator; Google sign-in optional |
| `DATABASE_URL` | from `agent-mesh-db` | auto-normalised to asyncpg |
| `REDIS_URL` | from `agent-mesh-redis` | |
| `CORS_ALLOW_ORIGINS` | `https://agent-mesh-web.onrender.com` | the frontend URL |
| `NEXT_PUBLIC_API_BASE_URL` | `https://agent-mesh-api.onrender.com` | the backend URL (build arg) |
| `JWT_SECRET` | generated | session signing |
| `OPENAI_API_KEY` | you set it | optional; demo mode without it |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | you set it | optional; enables the Google sign-in button |

## Notes and limits

- **Free plan** web services sleep after ~15 minutes idle; the next request wakes them in
  ~30–60s. Free PostgreSQL expires after 90 days. For always-on, change `plan: free` to
  `plan: starter` on the services and database.
- **URL collisions**: Render derives each service URL from its name. If
  `agent-mesh-api`/`agent-mesh-web` are already taken globally, Render appends a suffix;
  update `NEXT_PUBLIC_API_BASE_URL`, `BACKEND_INTERNAL_URL`, and `CORS_ALLOW_ORIGINS` to
  match the real URLs and redeploy.
- **Google sign-in** is optional. To enable it, create an OAuth client in Google Cloud,
  add both Render URLs as authorized origins, then set `GOOGLE_CLIENT_ID` on the API and
  `NEXT_PUBLIC_GOOGLE_CLIENT_ID` on the frontend (and set `AUTH_MODE=google`).
