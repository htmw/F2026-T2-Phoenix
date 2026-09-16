"""Operator identity, workflow ownership, and write-route gates."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from pydantic import SecretStr

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.seed import seed_agents
from app.api.dependencies import get_session
from app.core.config import Settings
from app.main import create_app
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry


@pytest.fixture
def auth_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "auth_mode": "header",
            "dev_operator_id": "fallback-op",
            "jwt_secret": SecretStr("auth-suite-jwt-secret"),
        }
    )


@pytest.fixture
async def auth_client(
    auth_settings: Settings,
    session_factory: async_sessionmaker,
    fake_provider: FakeProvider,
) -> AsyncClient:
    app = create_app(auth_settings)
    app.state.session_factory = session_factory
    app.state.provider_registry = ProviderRegistry([fake_provider])

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


async def test_write_requires_operator_header(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/tasks?wait=true",
        json={"request": "Find security vulnerabilities"},
    )
    assert response.status_code == 401
    assert "operator identity required" in response.json()["detail"]


async def test_task_stamps_owner_and_scopes_list(auth_client: AsyncClient) -> None:
    alice = {"X-Operator-Id": "alice"}
    bob = {"X-Operator-Id": "bob"}

    created = await auth_client.post(
        "/api/v1/tasks?wait=true",
        headers=alice,
        json={"request": "Find security vulnerabilities in the payments service"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["owner_id"] == "alice"
    workflow_id = body["id"]

    alice_list = await auth_client.get("/api/v1/workflows", headers=alice)
    assert alice_list.status_code == 200
    assert any(item["id"] == workflow_id for item in alice_list.json())

    bob_list = await auth_client.get("/api/v1/workflows", headers=bob)
    assert bob_list.status_code == 200
    assert not any(item["id"] == workflow_id for item in bob_list.json())

    bob_get = await auth_client.get(f"/api/v1/workflows/{workflow_id}", headers=bob)
    assert bob_get.status_code == 404

    alice_get = await auth_client.get(f"/api/v1/workflows/{workflow_id}", headers=alice)
    assert alice_get.status_code == 200


async def test_decision_actor_comes_from_header_not_body(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/decisions",
        headers={"X-Operator-Id": "real-operator"},
        json={
            "kind": "operator",
            "actor_id": "spoofed",
            "title": "Style choice",
            "summary": "should not keep spoofed actor",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["actor_id"] == "real-operator"


async def test_bearer_jwt_accepted_as_operator_id(auth_client: AsyncClient) -> None:
    import jwt
    from datetime import UTC, datetime, timedelta

    token = jwt.encode(
        {
            "sub": "plan-user",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        "auth-suite-jwt-secret",
        algorithm="HS256",
    )
    response = await auth_client.post(
        "/api/v1/tasks/plan",
        headers={"Authorization": f"Bearer {token}"},
        json={"request": "Write a README"},
    )
    assert response.status_code == 200, response.text


async def test_auth_off_uses_dev_operator(db_client: AsyncClient) -> None:
    """Default test fixture uses auth_mode=off → DEV_OPERATOR_ID stamps ownership."""
    response = await db_client.post(
        "/api/v1/tasks?wait=true",
        json={"request": "Find security vulnerabilities"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["owner_id"] == "test-operator"
