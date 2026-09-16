"""Shared test fixtures.

Tests build the app from the factory with explicit test settings so they never depend on
a developer's `.env`, and never reach a real provider.

Database-backed tests run against a real PostgreSQL instance because the features they
cover (JSONB columns, cascade deletes, unique constraints, index-backed capability
queries) do not exist in SQLite. When no database is reachable they skip rather than
silently passing against a different engine.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.registry import InMemoryAgentRegistry
from app.agents.seed import seed_agents
from app.api.dependencies import get_session
from app.core.config import Settings
from app.database.base import Base
from app.database.session import create_engine, create_session_factory
from app.main import create_app
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry

# Default points at the compose-published database. A CI service container or a
# developer's own instance can override it.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://agentorch:change-me-locally@localhost:5432/agentorch_test",
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        log_format="json",
        log_level="WARNING",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://localhost:6379/15",
        seed_agents_on_startup=False,
        # Heuristic analysis keeps endpoint tests deterministic and stops the analyser
        # from consuming responses scripted for the agents themselves. The LLM analyser
        # has its own unit tests, including its fallback behaviour.
        use_llm_capability_analysis=False,
        # Identity still stamps ownership via DEV_OPERATOR_ID; header mode is covered
        # by dedicated auth tests.
        auth_mode="off",
        dev_operator_id="test-operator",
        rate_limit_backend="memory",
        rate_limit_enabled=True,
        rate_limit_requests=10_000,
        operator_budget_usd=None,
        # Ignore any developer `.env` so tests are hermetic.
        _env_file=None,
    )


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """An HTTP client for tests that do not need a database.

    Lifespan is not run, so no engine is created and no connection is attempted.
    """
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


async def _database_is_reachable(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect():
            return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(settings)
    if not await _database_is_reachable(engine):
        await engine.dispose()
        pytest.skip(f"no PostgreSQL at {settings.database_url.rsplit('@', 1)[-1]}")

    # Schema is created from metadata rather than by running migrations: these tests
    # verify application behaviour, and a dedicated migration test covers the migration
    # path itself.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest_asyncio.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_session(session: AsyncSession) -> AsyncSession:
    await seed_agents(session, BUILTIN_AGENTS)
    await session.commit()
    return session


@pytest.fixture
def fake_provider() -> FakeProvider:
    """The provider used by API tests. Script responses on it before calling an endpoint."""
    return FakeProvider()


@pytest_asyncio.fixture
async def db_client(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    fake_provider: FakeProvider,
) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the test database with the built-in agents seeded.

    The provider registry holds the scripted ``fake_provider``, so an endpoint test can
    control exactly what the model returns without reaching the network.
    """
    app = create_app(settings)
    app.state.session_factory = session_factory
    app.state.provider_registry = ProviderRegistry([fake_provider])

    async with session_factory() as session:
        await seed_agents(session, BUILTIN_AGENTS)
        await session.commit()

    # Each request gets its own session from the test factory; lifespan is skipped so
    # the app never builds its own engine against a non-test database.
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as request_session:
            yield request_session
            await request_session.commit()

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
def memory_registry() -> InMemoryAgentRegistry:
    return InMemoryAgentRegistry(list(BUILTIN_AGENTS))
