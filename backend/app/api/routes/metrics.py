"""Operator metrics: the five questions, plus a Prometheus scrape endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.api.dependencies import SessionDep
from app.core.metrics import process_metrics
from app.services.metrics_service import MetricsRepository

scrape_router = APIRouter(tags=["metrics"])
api_router = APIRouter(prefix="/metrics", tags=["metrics"])


class TokenTotals(BaseModel):
    input: int
    output: int
    total: int


class SlowestAgent(BaseModel):
    agent_id: str
    node_key: str
    latency_ms: float
    workflow_id: str
    provider: str | None = None
    model: str | None = None


class MetricsSummary(BaseModel):
    """Answers the operator questions from durable execution records.

    Public until Sprint 9 authentication lands.
    """

    workflow_count: int
    attempt_count: int
    total_cost_usd: float
    token_totals: TokenTotals
    slowest_agent: SlowestAgent | None = None
    retry_counts: dict[str, int] = Field(default_factory=dict)
    failing_providers: dict[str, int] = Field(default_factory=dict)


@api_router.get("", response_model=MetricsSummary, summary="Cost and reliability summary")
async def metrics_summary(session: SessionDep) -> MetricsSummary:
    payload = await MetricsRepository(session).summary()
    return MetricsSummary.model_validate(payload)


@scrape_router.get("/metrics", summary="Prometheus scrape")
async def prometheus_metrics() -> Response:
    """Process-local counters. Restart resets them; Postgres remains the source of truth."""
    return Response(
        content=process_metrics.render_prometheus(),
        media_type="text/plain; version=0.0.4",
    )
