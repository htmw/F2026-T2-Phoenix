"""Enrolling, updating and disabling agents through one defined workflow.

Enrollment validates everything up front (schemas, names, the table the schema implies)
and then writes the agent row and creates its table in the caller's transaction. Either
both exist afterwards or neither does.
"""

from __future__ import annotations

import re
import uuid

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentNotFoundError, record_to_definition
from app.agents.seed import seed_agent_with_table
from app.agents.tables import AgentTableError, data_columns
from app.core.logging import get_logger
from app.models.agent import AgentRecord
from app.schemas.agent import (
    AgentDefinition,
    AgentEnrollment,
    AgentLimits,
    AgentUpdate,
)

logger = get_logger(__name__)


class EnrollmentError(ValueError):
    """A request that cannot be enrolled as given. ``field`` names the problem."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class DuplicateAgentNameError(EnrollmentError):
    def __init__(self, name: str) -> None:
        super().__init__("name", f"an agent named '{name}' is already enrolled")


def validate_schema(schema: dict[str, object], field: str, *, require_object: bool) -> None:
    """Reject a schema that is not valid JSON Schema, naming the offending location."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        location = ".".join(str(part) for part in exc.path)
        raise EnrollmentError(f"{field}.{location}" if location else field, exc.message) from None
    if require_object and schema.get("type") != "object":
        raise EnrollmentError(f"{field}.type", "must be 'object'")


def validate_output_schema(schema: dict[str, object]) -> None:
    validate_schema(schema, "output_schema", require_object=True)
    try:
        data_columns(schema)
    except AgentTableError as exc:
        raise EnrollmentError(exc.field, exc.message) from None


def _agent_id_for(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-")
    return f"{slug or 'agent'}-{uuid.uuid4().hex[:8]}"


def _default_instructions(name: str, description: str) -> str:
    return (
        f"You are {name}. {description} Do only the work described in the objective "
        "and respond with a single JSON object that matches your output schema."
    )


async def _ensure_unique_name(
    session: AsyncSession, name: str, *, exclude_id: str | None = None
) -> None:
    statement = select(AgentRecord.id).where(func.lower(AgentRecord.name) == name.lower())
    if exclude_id is not None:
        statement = statement.where(AgentRecord.id != exclude_id)
    if (await session.execute(statement)).first() is not None:
        raise DuplicateAgentNameError(name)


async def enroll_agent(session: AsyncSession, body: AgentEnrollment) -> AgentRecord:
    validate_schema(body.input_schema, "input_schema", require_object=False)
    validate_output_schema(body.output_schema)
    await _ensure_unique_name(session, body.name)

    definition = AgentDefinition(
        id=_agent_id_for(body.name),
        name=body.name,
        description=body.description,
        capabilities=frozenset(body.capabilities),
        instructions=body.instructions or _default_instructions(body.name, body.description),
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        limits=AgentLimits(
            timeout_seconds=body.cost_profile.timeout_seconds,
            max_cost_usd=body.cost_profile.max_cost_usd,
        ),
        supported_models=tuple(body.supported_models),
    )
    record = await seed_agent_with_table(session, definition, strict=True)
    logger.info(
        "agent_enrolled",
        agent_id=definition.id,
        capabilities=sorted(c.value for c in definition.capabilities),
        table=record.table_name,
    )
    return record


async def update_agent(session: AsyncSession, agent_id: str, body: AgentUpdate) -> AgentRecord:
    record = await session.get(AgentRecord, agent_id)
    if record is None:
        raise AgentNotFoundError(f"agent '{agent_id}' is not registered")

    if body.name is not None and body.name.lower() != record.name.lower():
        await _ensure_unique_name(session, body.name, exclude_id=agent_id)
    if body.input_schema is not None:
        validate_schema(body.input_schema, "input_schema", require_object=False)
    if body.output_schema is not None:
        validate_output_schema(body.output_schema)

    current = record_to_definition(record)
    changes: dict[str, object] = {
        key: value
        for key, value in {
            "name": body.name,
            "description": body.description,
            "instructions": body.instructions,
            "input_schema": body.input_schema,
            "output_schema": body.output_schema,
            "enabled": body.enabled,
        }.items()
        if value is not None
    }
    if body.capabilities is not None:
        changes["capabilities"] = frozenset(body.capabilities)
    if body.supported_models is not None:
        changes["supported_models"] = tuple(body.supported_models)
    if body.cost_profile is not None:
        changes["limits"] = AgentLimits(
            timeout_seconds=body.cost_profile.timeout_seconds,
            max_cost_usd=body.cost_profile.max_cost_usd,
        )
    # Re-validate the whole definition rather than trusting a partial merge.
    updated = AgentDefinition.model_validate({**current.model_dump(), **changes})

    try:
        record = await seed_agent_with_table(session, updated, strict=True)
    except AgentTableError as exc:
        raise EnrollmentError(exc.field, exc.message) from None
    if body.enabled is not None:
        # The seed path only sets ``enabled`` on insert, to respect operator toggles.
        record.enabled = body.enabled
        await session.flush()
    logger.info(
        "agent_updated",
        agent_id=agent_id,
        fields=sorted(body.model_dump(exclude_none=True)),
        enabled=record.enabled,
    )
    return record
