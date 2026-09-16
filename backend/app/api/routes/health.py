"""Liveness and readiness endpoints.

Deliberately unversioned and mounted at the root: probes are infrastructure contracts
consumed by Docker, Compose, and later Kubernetes, so they must not move when the
application API is versioned.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from app.api.dependencies import SettingsDep
from app.core.health import check_postgres, check_redis

router = APIRouter(tags=["health"])


class DependencyReport(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None
    latency_ms: float | None = None


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    dependencies: list[DependencyReport] = Field(default_factory=list)


@router.get("/healthz", response_model=LivenessResponse, summary="Liveness probe")
async def liveness(settings: SettingsDep) -> LivenessResponse:
    """Report that the process is running.

    Intentionally checks nothing external: a liveness probe that fails when the database
    is briefly unavailable causes the orchestrator to restart a perfectly healthy process.
    """
    return LivenessResponse(app=settings.app_name, environment=settings.environment)


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(settings: SettingsDep, response: Response) -> ReadinessResponse:
    """Report whether dependencies needed to serve traffic are reachable.

    Checks run concurrently so the probe's latency is the slowest dependency rather than
    their sum. A degraded result returns 503 so load balancers stop sending traffic.
    """
    postgres, redis_status = await asyncio.gather(
        check_postgres(settings.database_url),
        check_redis(settings.redis_url),
    )
    dependencies = [postgres, redis_status]
    all_healthy = all(dependency.healthy for dependency in dependencies)

    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if all_healthy else "degraded",
        dependencies=[DependencyReport(**asdict(dependency)) for dependency in dependencies],
    )
