"""Tests for the liveness and readiness probes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.api.middleware import REQUEST_ID_HEADER
from app.api.routes import health as health_routes
from app.core.health import DependencyStatus


async def test_liveness_reports_ok_without_touching_dependencies(client: AsyncClient) -> None:
    # No dependency is stubbed here on purpose: if liveness needed Postgres or Redis,
    # this test would fail by trying to reach them.
    response = await client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"


async def test_liveness_returns_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.headers[REQUEST_ID_HEADER]


async def test_inbound_request_id_is_honoured(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={REQUEST_ID_HEADER: "caller-supplied-id"})

    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id"


async def test_readiness_is_ready_when_dependencies_are_healthy(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def healthy_postgres(_url: str) -> DependencyStatus:
        return DependencyStatus(name="postgres", healthy=True, latency_ms=1.0)

    async def healthy_redis(_url: str) -> DependencyStatus:
        return DependencyStatus(name="redis", healthy=True, latency_ms=0.5)

    monkeypatch.setattr(health_routes, "check_postgres", healthy_postgres)
    monkeypatch.setattr(health_routes, "check_redis", healthy_redis)

    response = await client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert {dependency["name"] for dependency in body["dependencies"]} == {"postgres", "redis"}


async def test_readiness_is_degraded_with_503_when_a_dependency_fails(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def healthy_postgres(_url: str) -> DependencyStatus:
        return DependencyStatus(name="postgres", healthy=True, latency_ms=1.0)

    async def broken_redis(_url: str) -> DependencyStatus:
        return DependencyStatus(name="redis", healthy=False, detail="ConnectionError")

    monkeypatch.setattr(health_routes, "check_postgres", healthy_postgres)
    monkeypatch.setattr(health_routes, "check_redis", broken_redis)

    response = await client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    failed = next(d for d in body["dependencies"] if d["name"] == "redis")
    assert failed["healthy"] is False
    assert failed["detail"] == "ConnectionError"
