"""Migration tests against a real PostgreSQL database.

These run the actual migration scripts rather than ``metadata.create_all``. Without
this, the schema tests could pass while the migrations that build production are
broken — and the migration is the only path a deployed environment ever takes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.database.session import create_engine

EXPECTED_TABLES = {
    "agents",
    "agent_capabilities",
    "providers",
    "models",
    "tasks",
    "workflows",
    "workflow_nodes",
    "workflow_edges",
    "executions",
    "agent_results",
    "agent_messages",
    "agent_presence",
    "memories",
    "artifacts",
    "network_events",
}


def alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parent.parent
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    # env.py reads settings, so the URL is injected through the environment that the
    # migration process itself will read.
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def migration_engine(settings: Settings) -> AsyncEngine:
    return create_engine(settings)


async def drop_everything(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))


async def table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))


async def run_alembic(settings: Settings, *, revision: str) -> None:
    """Run alembic against the test database in a worker thread.

    env.py creates its own event loop, so it cannot be invoked from inside a running
    one. The database URL is passed on the config, which env.py honours ahead of
    settings — that is what keeps this test off the development database.
    """
    config = alembic_config(settings.database_url)

    def _migrate() -> None:
        if revision == "base":
            command.downgrade(config, "base")
        else:
            command.upgrade(config, revision)

    await asyncio.to_thread(_migrate)


@pytest.mark.usefixtures("engine")
async def test_migrations_build_the_expected_schema(settings: Settings) -> None:
    engine = create_engine(settings)
    try:
        await drop_everything(engine)
        await run_alembic(settings, revision="head")

        tables = await table_names(engine)
        assert tables >= EXPECTED_TABLES
        assert "alembic_version" in tables
    finally:
        await engine.dispose()


@pytest.mark.usefixtures("engine")
async def test_migrations_downgrade_cleanly(settings: Settings) -> None:
    engine = create_engine(settings)
    try:
        await drop_everything(engine)
        await run_alembic(settings, revision="head")
        await run_alembic(settings, revision="base")

        remaining = await table_names(engine)
        # A downgrade that leaves tables behind makes the next upgrade fail, which is
        # how a rollback turns a bad deploy into an outage.
        assert not (EXPECTED_TABLES & remaining)
    finally:
        await engine.dispose()


@pytest.mark.usefixtures("engine")
async def test_migrated_schema_enforces_capability_uniqueness(settings: Settings) -> None:
    engine = create_engine(settings)
    try:
        await drop_everything(engine)
        await run_alembic(settings, revision="head")

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO agents (id, name, description, version, instructions, "
                    "input_schema, output_schema, model_preference, retry_policy, tools, "
                    "permissions, timeout_seconds, max_cost_usd, enabled) VALUES "
                    "('x-agent', 'X', 'd', '1.0.0', 'i', '{}', '{}', '{}', '{}', '[]', "
                    "'[]', 10, 1, true)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO agent_capabilities (agent_id, capability) "
                    "VALUES ('x-agent', 'code.generation')"
                )
            )

        with pytest.raises(Exception):  # noqa: B017 - asyncpg raises its own integrity error
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO agent_capabilities (agent_id, capability) "
                        "VALUES ('x-agent', 'code.generation')"
                    )
                )
    finally:
        await engine.dispose()
