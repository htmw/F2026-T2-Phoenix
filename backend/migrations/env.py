"""Alembic environment.

The database URL defaults to application settings, so credentials have one source and
migrations cannot drift to a different database than the app uses. An explicit URL --
passed as ``-x url=...`` or set on the config by a caller such as CI or the migration
tests -- takes precedence, because "migrate this specific database" must be expressible
without editing the environment.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

# Importing the models package registers every table on Base.metadata.
import app.models  # noqa: F401  (side-effect import)
from app.core.config import get_settings
from app.database.base import Base
from app.database.session import create_engine_from_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    from_x_argument = context.get_x_argument(as_dictionary=True).get("url")
    from_config = config.get_main_option("sqlalchemy.url", None)
    return from_x_argument or from_config or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine_from_url(database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
