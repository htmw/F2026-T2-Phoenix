"""Shared Redis client for ephemeral coordination (rate limits, locks).

Postgres remains the source of truth (ADR 0003). Flushing Redis must never lose
workflow history — only counters and caches.
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from fastapi import Request

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def create_redis(settings: Settings) -> aioredis.Redis | None:
    """Open a Redis client when the redis backend is selected; otherwise None."""
    if settings.rate_limit_backend != "redis":
        return None
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        logger.warning("redis_unavailable_at_startup", error_type="ping_failed")
        await client.aclose()
        return None
    return client


async def close_redis(client: aioredis.Redis | None) -> None:
    if client is not None:
        await client.aclose()


def redis_from_request(request: Request) -> aioredis.Redis | None:
    client: aioredis.Redis | None = getattr(request.app.state, "redis", None)
    return client


def memory_store_from_request(request: Request) -> dict[str, Any]:
    store: dict[str, Any] | None = getattr(request.app.state, "rate_limit_memory", None)
    if store is None:
        store = {}
        request.app.state.rate_limit_memory = store
    return store
