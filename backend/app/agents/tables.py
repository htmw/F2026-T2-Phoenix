"""Per-agent result tables, built from each agent's output schema.

Every enrolled agent gets its own table in the ``agent_data`` schema, with one column per
top-level output property, so structured results can be queried without anyone writing
a migration. Identifiers are derived, never interpolated: the table name comes from the
already-validated agent id, column names must match a strict pattern, and all DDL goes
through SQLAlchemy's quoting.

System columns are prefixed with ``_``. Property names must start with a letter, so an
agent's fields can never collide with them.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Double,
    MetaData,
    Table,
    Text,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateSchema
from sqlalchemy.types import TypeEngine

from app.core.logging import get_logger

logger = get_logger(__name__)

AGENT_DATA_SCHEMA = "agent_data"

_PROPERTY_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
_TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# JSON Schema scalar types map to native columns; anything structured or ambiguous is
# stored as JSONB so no valid payload is ever rejected by the database.
_SCALAR_TYPES: dict[str, type[TypeEngine[Any]]] = {
    "string": Text,
    "integer": BigInteger,
    "number": Double,
    "boolean": Boolean,
}


class AgentTableError(ValueError):
    """An output schema cannot be turned into a table. ``field`` names the culprit."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


@dataclass(frozen=True, slots=True)
class DataColumn:
    property_name: str
    column_name: str
    sql_type: type[TypeEngine[Any]]


def table_name_for(agent_id: str) -> str:
    """Safe, deterministic table name for an agent id."""
    name = "out_" + re.sub(r"[^a-z0-9]+", "_", agent_id.lower()).strip("_")
    name = name[:63]
    if not _TABLE_NAME.fullmatch(name):
        raise AgentTableError("id", f"cannot derive a safe table name from {agent_id!r}")
    return name


def data_columns(output_schema: dict[str, object]) -> list[DataColumn]:
    """Columns for each top-level output property, validated for use as identifiers."""
    properties = output_schema.get("properties", {})
    if not isinstance(properties, dict):
        raise AgentTableError("output_schema.properties", "must be an object")

    columns: list[DataColumn] = []
    seen: dict[str, str] = {}
    for property_name, definition in properties.items():
        field = f"output_schema.properties.{property_name}"
        if not _PROPERTY_NAME.fullmatch(str(property_name)):
            raise AgentTableError(
                field,
                "property names must start with a letter and contain only letters, "
                "digits and underscores (max 63 characters)",
            )
        column_name = str(property_name).lower()
        if column_name in seen:
            raise AgentTableError(
                field, f"collides with '{seen[column_name]}' (column names are case-insensitive)"
            )
        seen[column_name] = str(property_name)
        columns.append(DataColumn(str(property_name), column_name, _column_type(definition)))
    return columns


def _column_type(definition: object) -> type[TypeEngine[Any]]:
    if not isinstance(definition, dict):
        return JSONB
    declared = definition.get("type")
    if isinstance(declared, list):
        non_null = [item for item in declared if item != "null"]
        declared = non_null[0] if len(non_null) == 1 else None
    if isinstance(declared, str) and declared in _SCALAR_TYPES:
        return _SCALAR_TYPES[declared]
    return JSONB


def build_table(table_name: str, output_schema: dict[str, object]) -> Table:
    columns: list[Column[Any]] = [
        Column("_id", UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()),
        Column("_execution_id", UUID(as_uuid=True), nullable=True, index=True),
        Column("_workflow_id", UUID(as_uuid=True), nullable=True, index=True),
        Column("_node_key", Text, nullable=True),
        # The full validated payload, so nothing outside the declared columns is lost.
        Column("_payload", JSONB, nullable=False),
        Column("_created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    ]
    columns.extend(
        Column(column.column_name, column.sql_type(), nullable=True)
        for column in data_columns(output_schema)
    )
    return Table(table_name, MetaData(), *columns, schema=AGENT_DATA_SCHEMA)


def qualified(table_name: str) -> str:
    return f"{AGENT_DATA_SCHEMA}.{table_name}"


def _type_sql(sql_type: TypeEngine[Any], dialect: Dialect) -> str:
    return sql_type.compile(dialect=dialect).upper()


async def ensure_agent_table(
    session: AsyncSession,
    agent_id: str,
    output_schema: dict[str, object],
    *,
    strict: bool = True,
) -> str:
    """Create the agent's table if needed and add any newly declared columns.

    Safe to run repeatedly: an existing table and its rows are kept. With ``strict``, a
    property whose type changed is an error; otherwise it is logged and left alone, so a
    built-in schema tweak cannot stop the service from starting.
    """
    table_name = table_name_for(agent_id)
    table = build_table(table_name, output_schema)

    def _sync(sync_session: Any) -> None:
        connection = sync_session.connection()
        connection.execute(CreateSchema(AGENT_DATA_SCHEMA, if_not_exists=True))
        table.create(connection, checkfirst=True)
        dialect = connection.dialect
        existing = {
            column["name"]: _type_sql(column["type"], dialect)
            for column in inspect(connection).get_columns(table_name, schema=AGENT_DATA_SCHEMA)
        }
        for column in table.columns:
            wanted = _type_sql(column.type, dialect)
            current = existing.get(column.name)
            if current is None:
                quoted_table = dialect.identifier_preparer.format_table(table)
                quoted_column = dialect.identifier_preparer.quote(column.name)
                connection.execute(
                    text(f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {wanted}")
                )
            elif current != wanted:
                message = f"type changed from {current} to {wanted}"
                if strict:
                    raise AgentTableError(f"output_schema.properties.{column.name}", message)
                logger.warning(
                    "agent_table_type_mismatch",
                    agent_id=agent_id,
                    column=column.name,
                    existing=current,
                    declared=wanted,
                )

    await session.run_sync(_sync)
    return qualified(table_name)


async def store_agent_row(
    session: AsyncSession,
    *,
    agent_id: str,
    table_name: str,
    output_schema: dict[str, object],
    payload: dict[str, object],
    execution_id: uuid.UUID | None,
    workflow_id: uuid.UUID | None,
    node_key: str | None,
) -> bool:
    """Write one validated payload. Returns False (and logs) if the write fails.

    Runs in a savepoint: the per-agent table is a projection of the result that is
    already recorded in ``agent_results``, so a failure here must not abort the run.
    """
    schema_name, _, bare = table_name.partition(".")
    if schema_name != AGENT_DATA_SCHEMA or not _TABLE_NAME.fullmatch(bare):
        logger.warning("agent_table_name_rejected", agent_id=agent_id, table=table_name)
        return False

    try:
        table = build_table(bare, output_schema)
        values: dict[str, object] = {
            "_execution_id": execution_id,
            "_workflow_id": workflow_id,
            "_node_key": node_key,
            "_payload": payload,
        }
        for column in data_columns(output_schema):
            if column.property_name in payload:
                values[column.column_name] = payload[column.property_name]
        async with session.begin_nested():
            await session.execute(table.insert().values(**values))
    except (SQLAlchemyError, AgentTableError) as exc:
        logger.warning(
            "agent_table_write_failed",
            agent_id=agent_id,
            table=table_name,
            error=str(exc)[:500],
        )
        return False
    return True
