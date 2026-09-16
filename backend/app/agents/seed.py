"""Seeding agent definitions into the registry.

Seeding is an idempotent upsert so it can run on every startup without duplicating
rows or clobbering an operator's ``enabled`` toggle unnecessarily. Capabilities are
replaced wholesale rather than merged, because a definition removing a capability must
actually remove it — a stale capability row would keep an agent selectable for work it
no longer claims to do.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.agent import AgentCapabilityRecord, AgentRecord
from app.schemas.agent import AgentDefinition

logger = get_logger(__name__)


async def upsert_agent(session: AsyncSession, definition: AgentDefinition) -> bool:
    """Insert or update one agent. Returns True when a row was created."""
    record = await session.get(AgentRecord, definition.id)
    created = record is None

    if record is None:
        record = AgentRecord(id=definition.id)
        session.add(record)

    record.name = definition.name
    record.description = definition.description
    record.version = definition.version
    record.instructions = definition.instructions
    record.input_schema = definition.input_schema
    record.output_schema = definition.output_schema
    preference = definition.model_preference.model_dump(mode="json")
    if not created and isinstance(record.model_preference, dict):
        # Preserve operator Fixed bindings across seed refreshes.
        existing_model = record.model_preference.get("preferred_model")
        if existing_model:
            preference["preferred_model"] = existing_model
            preference["preferred_provider"] = record.model_preference.get("preferred_provider")
    record.model_preference = preference
    record.retry_policy = definition.retry_policy.model_dump(mode="json")
    record.tools = list(definition.tools)
    record.permissions = list(definition.permissions)
    record.timeout_seconds = definition.limits.timeout_seconds
    record.max_cost_usd = definition.limits.max_cost_usd
    if created:
        # Respect an operator who disabled an existing agent; only set it on insert.
        record.enabled = definition.enabled

    await session.flush()

    await session.execute(
        delete(AgentCapabilityRecord).where(AgentCapabilityRecord.agent_id == definition.id)
    )
    for capability in sorted(definition.capabilities):
        session.add(AgentCapabilityRecord(agent_id=definition.id, capability=capability.value))
    await session.flush()
    return created


async def seed_agents(
    session: AsyncSession, definitions: tuple[AgentDefinition, ...]
) -> tuple[int, int]:
    """Seed definitions, returning (created, updated) counts."""
    created = 0
    for definition in definitions:
        if await upsert_agent(session, definition):
            created += 1

    total = len(definitions)
    logger.info("agents_seeded", created=created, updated=total - created, total=total)
    return created, total - created


async def registered_agent_ids(session: AsyncSession) -> set[str]:
    result = await session.execute(select(AgentRecord.id))
    return set(result.scalars())
