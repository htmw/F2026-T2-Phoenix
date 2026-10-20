# Production image. Multi-stage so build tooling and dev dependencies never reach the
# runtime layer, and the final image runs as a non-root user.

# ---- Stage 1: build dependencies into a virtualenv ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Unprivileged user: a compromised process should not own its own filesystem.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appuser app ./app
# Migrations are included so the schema can be applied as a deploy step
# (e.g. Render preDeployCommand: `alembic upgrade head`).
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser migrations ./migrations
# Entrypoint: run migrations then launch the server, binding to $PORT when the platform
# sets one (e.g. Render). Invoked via `sh` so no execute bit is required.
COPY --chown=appuser:appuser start.sh ./

USER appuser

EXPOSE 8000

# Reuses the application's own liveness probe rather than duplicating check logic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"

CMD ["sh", "./start.sh"]
