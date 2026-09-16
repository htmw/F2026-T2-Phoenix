"""Tests for request correlation middleware, including the failure path."""

from __future__ import annotations

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from app.api.middleware import REQUEST_ID_HEADER
from app.core.config import Settings
from app.main import create_app


async def test_request_id_is_bound_to_the_log_context(settings: Settings) -> None:
    app = create_app(settings)
    captured: dict[str, object] = {}

    @app.get("/_test/context")
    async def read_context() -> dict[str, str]:
        captured.update(structlog.contextvars.get_contextvars())
        return {"ok": "yes"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/_test/context", headers={REQUEST_ID_HEADER: "abc-123"})

    # Handlers get the id for free: nothing had to pass it down the call stack.
    assert captured["request_id"] == "abc-123"


async def test_unhandled_error_is_logged_and_re_raised(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/_test/boom")
    async def explode() -> None:
        raise RuntimeError("deliberate failure")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # The middleware logs the failure but must not swallow it: the framework's error
        # handling stays responsible for the response.
        with pytest.raises(RuntimeError, match="deliberate failure"):
            await client.get("/_test/boom")
