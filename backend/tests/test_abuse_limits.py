"""Per-operator rate limits and soft budget caps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.seed import seed_agents
from app.api.dependencies import get_session
from app.core.config import Settings
from app.domain.enums import ExecutionStatus, NodeStatus, TaskStatus, WorkflowStatus
from app.main import create_app
from app.models.workflow import (
    ExecutionRecord,
    TaskRecord,
    WorkflowNodeRecord,
    WorkflowRecord,
)
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry


@pytest.fixture
def tight_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "auth_mode": "off",
            "dev_operator_id": "spender",
            "rate_limit_backend": "memory",
            "rate_limit_enabled": True,
            "rate_limit_requests": 2,
            "rate_limit_window_seconds": 60,
            "operator_budget_usd": 0.01,
            "operator_budget_window_hours": 24,
        }
    )


@pytest.fixture
async def tight_client(
    tight_settings: Settings,
    session_factory: async_sessionmaker,
    fake_provider: FakeProvider,
) -> AsyncClient:
    app = create_app(tight_settings)
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


async def test_rate_limit_returns_429(tight_client: AsyncClient) -> None:
    payload = {"request": "Find security vulnerabilities"}
    first = await tight_client.post("/api/v1/tasks/plan", json=payload)
    second = await tight_client.post("/api/v1/tasks/plan", json=payload)
    third = await tight_client.post("/api/v1/tasks/plan", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 429, third.text
    assert "rate limit exceeded" in third.json()["detail"]
    assert third.headers.get("Retry-After")


async def test_me_limits_endpoint(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/me/limits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["operator_id"] == "test-operator"
    assert body["rate_limit"] >= 1
    assert body["rate_remaining"] >= 0
    assert body["budget_cap_usd"] is None


async def test_operator_budget_blocks_new_submit(
    tight_client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    # Seed prior spend under the same operator id used by auth_mode=off.
    async with session_factory() as session:
        await _seed_spend(session, owner_id="spender", cost_usd=0.05)
        await session.commit()

    # First request still consumes a rate slot; budget should reject before plan runs.
    response = await tight_client.post(
        "/api/v1/tasks?wait=true",
        json={"request": "Find security vulnerabilities"},
    )
    assert response.status_code == 402, response.text
    assert "budget exceeded" in response.json()["detail"]


async def _seed_spend(session: AsyncSession, *, owner_id: str, cost_usd: float) -> None:
    task = TaskRecord(
        request="prior spend",
        status=TaskStatus.COMPLETED,
        parameters={},
        owner_id=owner_id,
    )
    session.add(task)
    await session.flush()
    workflow = WorkflowRecord(
        task_id=task.id,
        status=WorkflowStatus.COMPLETED,
        selection={},
        owner_id=owner_id,
        total_cost_usd=cost_usd,
    )
    session.add(workflow)
    await session.flush()
    node = WorkflowNodeRecord(
        workflow_id=workflow.id,
        node_key="main",
        agent_id="security-agent",
        objective="prior",
        parameters={},
        satisfies=[],
        status=NodeStatus.COMPLETED,
        position=0,
    )
    session.add(node)
    await session.flush()
    session.add(
        ExecutionRecord(
            node_id=node.id,
            attempt=1,
            status=ExecutionStatus.SUCCEEDED,
            cost_usd=cost_usd,
            started_at=datetime.now(UTC) - timedelta(hours=1),
            completed_at=datetime.now(UTC),
        )
    )
    await session.flush()
