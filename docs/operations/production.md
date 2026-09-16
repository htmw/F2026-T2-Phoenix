# Production deployment

Multi-stage images already exist (`backend/Dockerfile`, `frontend/Dockerfile`).
Development Compose is not the production topology.

## Images

```bash
make build-prod
# or
docker build -t agentorch-backend:local ./backend
docker build -t agentorch-frontend:local ./frontend
```

Run migrations as a **one-shot job** against the production database before flipping
traffic. Do not migrate from application startup: two replicas would race.

```bash
docker run --rm \
  -e DATABASE_URL=postgresql+asyncpg://... \
  agentorch-backend:local \
  alembic upgrade head
```

## Required production settings

Set `ENVIRONMENT=production`. Settings validation **refuses to start** unless:

| Variable | Requirement |
|----------|-------------|
| `AUTH_MODE` | Must be `header` (`off` is forbidden) |
| `DEBUG` | Must be `false` |
| `SEED_AGENTS_ON_STARTUP` | Must be `false` |
| `ENCRYPTION_KEY` | Required (Fernet material for Settings-stored provider keys) |
| `JWT_SECRET` | Required (HS256 validation for Bearer JWTs) |
| `CORS_ALLOW_ORIGINS` | Non-empty explicit origins; no `*` |
| `ALLOWED_HOSTS` | Non-empty Host allow-list; no `*` |

Also inject at runtime: `DATABASE_URL`, `REDIS_URL`, and any provider API keys.
`TrustedHostMiddleware` and a narrowed CORS method/header allow-list apply only when
`ENVIRONMENT=production`.

## Secrets

Never bake keys into images or commit `.env`.

| Environment | Where secrets live |
|-------------|--------------------|
| Local | `.env` (gitignored), copied from `.env.example` |
| Compose on a server | Docker secrets or an env file outside the repo, mode 600 |
| Cloud | The platform secret store: AWS Secrets Manager / SSM, GCP Secret Manager, Azure Key Vault, or the host's sealed-secret controller |

The backend reads `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`,
`MISTRAL_API_KEY`, `OPENROUTER_API_KEY`, `DATABASE_URL`, `REDIS_URL`, and `ENCRYPTION_KEY`
from the process environment. Inject them at runtime.

Pattern for AWS: grant the task role `secretsmanager:GetSecretValue`, then either
use the native secrets integration on the task definition or a tiny entrypoint that
exports the JSON secret as env vars. Do not put the secret ARN in a client-visible
variable. Nothing with `NEXT_PUBLIC_` may hold a provider key.

`ENVIRONMENT=production` also disables `/docs` and `/openapi.json`.

## Observability

`GET /metrics` is Prometheus text. `GET /api/v1/metrics` is the durable Postgres
summary. Grafana dashboard JSON lives in `observability/grafana/dashboards/`.

```bash
docker compose --profile observability up
```

Grafana is published on http://localhost:3001 (admin/admin in that profile only).
Change that password before any networked use.
