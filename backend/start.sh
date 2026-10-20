#!/bin/sh
# Container entrypoint for hosted deploys (e.g. Render): apply any pending database
# migrations, then start the API on the platform-assigned port ($PORT), defaulting to
# 8000 for a plain `docker run`. `exec` hands PID 1 to uvicorn so signals propagate.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
