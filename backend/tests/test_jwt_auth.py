"""HS256 JWT Bearer validation (Universal Office Sprint 12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.seed import seed_agents
from app.api.dependencies import get_session
from app.core.config import Settings
from app.core.identity import operator_id_from_jwt, resolve_operator
from app.main import create_app
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from starlette.requests import Request


JWT_SECRET = "test-jwt-secret-for-sprint-12"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "auth_mode": "header",
        "jwt_secret": JWT_SECRET,
        "rate_limit_backend": "memory",
        "rate_limit_requests": 10_000,
        "seed_agents_on_startup": False,
        "_env_file": None,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def mint_token(
    sub: str = "jwt-user",
    *,
    secret: str = JWT_SECRET,
    expires_delta: timedelta | None = timedelta(hours=1),
    **extra: object,
) -> str:
    payload: dict[str, object] = {"sub": sub, **extra}
    if expires_delta is not None:
        payload["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
async def jwt_client(
    session_factory: async_sessionmaker,
    fake_provider: FakeProvider,
) -> AsyncClient:
    settings = _settings()
    app = create_app(settings)
    app.state.session_factory = session_factory
    app.state.provider_registry = ProviderRegistry([fake_provider])
    app.state.rate_limit_memory = {}

    async with session_factory() as session:
        await seed_agents(session, BUILTIN_AGENTS)
        await session.commit()

    async def override_session():
        async with session_factory() as request_session:
            yield request_session
            await request_session.commit()

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def test_valid_jwt_yields_sub() -> None:
    settings = _settings()
    token = mint_token("alice")
    assert operator_id_from_jwt(token, settings) == "alice"


def test_bad_signature_is_401() -> None:
    settings = _settings()
    token = mint_token("alice", secret="wrong-secret")
    with pytest.raises(Exception) as exc:
        operator_id_from_jwt(token, settings)
    assert getattr(exc.value, "status_code", None) == 401


def test_expired_jwt_is_401() -> None:
    settings = _settings()
    token = mint_token("alice", expires_delta=timedelta(seconds=-10))
    with pytest.raises(Exception) as exc:
        operator_id_from_jwt(token, settings)
    assert getattr(exc.value, "status_code", None) == 401


def test_missing_sub_is_401() -> None:
    settings = _settings()
    token = jwt.encode({"exp": datetime.now(UTC) + timedelta(hours=1)}, JWT_SECRET, algorithm="HS256")
    with pytest.raises(Exception) as exc:
        operator_id_from_jwt(token, settings)
    assert getattr(exc.value, "status_code", None) == 401


def test_opaque_bearer_no_longer_accepted() -> None:
    settings = _settings()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"authorization", b"Bearer plan-user")],
    }
    request = Request(scope)
    with pytest.raises(Exception) as exc:
        resolve_operator(request, settings)
    assert getattr(exc.value, "status_code", None) == 401


async def test_api_accepts_valid_jwt(jwt_client: AsyncClient) -> None:
    token = mint_token("plan-user")
    response = await jwt_client.post(
        "/api/v1/tasks/plan",
        headers={"Authorization": f"Bearer {token}"},
        json={"request": "Write a README"},
    )
    assert response.status_code == 200, response.text


async def test_api_rejects_opaque_bearer(jwt_client: AsyncClient) -> None:
    response = await jwt_client.post(
        "/api/v1/tasks/plan",
        headers={"Authorization": "Bearer plan-user"},
        json={"request": "Write a README"},
    )
    assert response.status_code == 401


async def test_header_still_wins_over_jwt(jwt_client: AsyncClient) -> None:
    token = mint_token("jwt-user")
    response = await jwt_client.post(
        "/api/v1/decisions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Operator-Id": "header-user",
        },
        json={"kind": "operator", "actor_id": "ignored", "title": "From header"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["actor_id"] == "header-user"
