"""Unit tests for the dependency-check helpers."""

from __future__ import annotations

import asyncio

from app.core.health import (
    CHECK_TIMEOUT_SECONDS,
    _timed,
    check_postgres,
    check_redis,
    to_asyncpg_dsn,
)


def test_sqlalchemy_url_is_converted_for_asyncpg() -> None:
    converted = to_asyncpg_dsn("postgresql+asyncpg://user:pw@postgres:5432/db")

    assert converted == "postgresql://user:pw@postgres:5432/db"


def test_plain_postgres_url_is_left_unchanged() -> None:
    url = "postgresql://user:pw@postgres:5432/db"

    assert to_asyncpg_dsn(url) == url


async def test_timed_reports_success_with_latency() -> None:
    async def probe() -> None:
        return None

    result = await _timed("thing", probe())

    assert result.healthy is True
    assert result.latency_ms is not None


async def test_timed_converts_exception_into_unhealthy_status() -> None:
    async def probe() -> None:
        raise ConnectionRefusedError("connection refused to postgres://user:pw@host/db")

    result = await _timed("thing", probe())

    assert result.healthy is False
    # Only the exception class is reported: messages can contain a DSN with a password.
    assert result.detail == "ConnectionRefusedError"


async def test_timed_bounds_a_hanging_probe() -> None:
    async def probe() -> None:
        await asyncio.sleep(CHECK_TIMEOUT_SECONDS + 5)

    result = await asyncio.wait_for(_timed("thing", probe()), timeout=CHECK_TIMEOUT_SECONDS + 2)

    assert result.healthy is False
    assert result.detail is not None
    assert "timed out" in result.detail


async def test_unreachable_postgres_is_reported_not_raised() -> None:
    # Port 1 is reserved and refuses immediately; no real database is contacted.
    result = await check_postgres("postgresql+asyncpg://user:pw@127.0.0.1:1/db")

    assert result.name == "postgres"
    assert result.healthy is False


async def test_unreachable_redis_is_reported_not_raised() -> None:
    result = await check_redis("redis://127.0.0.1:1/0")

    assert result.name == "redis"
    assert result.healthy is False
