"""Seeding tests: idempotency and capability replacement."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.seed import registered_agent_ids, seed_agents, upsert_agent
from app.domain.enums import Capability
from app.models.agent import AgentCapabilityRecord, AgentRecord
from tests.test_registry import make_definition


async def count(session: AsyncSession, column: object) -> int:
    result = await session.execute(select(func.count()).select_from(column))  # type: ignore[arg-type]
    return int(result.scalar_one())


async def test_seeding_creates_all_builtin_agents(session: AsyncSession) -> None:
    created, updated = await seed_agents(session, BUILTIN_AGENTS)
    await session.commit()

    assert (created, updated) == (8, 0)
    assert await registered_agent_ids(session) == {d.id for d in BUILTIN_AGENTS}


async def test_seeding_twice_creates_no_duplicates(session: AsyncSession) -> None:
    await seed_agents(session, BUILTIN_AGENTS)
    await session.commit()
    agents_after_first = await count(session, AgentRecord)
    capabilities_after_first = await count(session, AgentCapabilityRecord)

    created, updated = await seed_agents(session, BUILTIN_AGENTS)
    await session.commit()

    # Startup seeding runs on every boot, so a non-idempotent upsert would grow the
    # table without bound.
    assert (created, updated) == (0, 8)
    assert await count(session, AgentRecord) == agents_after_first
    assert await count(session, AgentCapabilityRecord) == capabilities_after_first


async def test_updating_a_definition_removes_dropped_capabilities(
    session: AsyncSession,
) -> None:
    original = make_definition(
        "shrinking-agent", {Capability.SUMMARISATION, Capability.WEB_RESEARCH}
    )
    await upsert_agent(session, original)
    await session.commit()

    reduced = make_definition("shrinking-agent", {Capability.SUMMARISATION})
    await upsert_agent(session, reduced)
    await session.commit()

    result = await session.execute(
        select(AgentCapabilityRecord.capability).where(
            AgentCapabilityRecord.agent_id == "shrinking-agent"
        )
    )
    # A stale capability row would keep the agent selectable for work it no longer
    # claims to do, which is worse than not registering it at all.
    assert set(result.scalars()) == {Capability.SUMMARISATION.value}


async def test_updating_a_definition_changes_metadata(session: AsyncSession) -> None:
    await upsert_agent(session, make_definition("mutable-agent", {Capability.DOCUMENTATION}))
    await session.commit()

    renamed = make_definition("mutable-agent", {Capability.DOCUMENTATION}).model_copy(
        update={"name": "Renamed Agent", "version": "2.0.0"}
    )
    await upsert_agent(session, renamed)
    await session.commit()

    record = await session.get(AgentRecord, "mutable-agent")
    assert record is not None
    assert (record.name, record.version) == ("Renamed Agent", "2.0.0")


async def test_reseeding_preserves_an_operator_disable(session: AsyncSession) -> None:
    await seed_agents(session, BUILTIN_AGENTS)
    await session.commit()

    record = await session.get(AgentRecord, "coding-agent")
    assert record is not None
    record.enabled = False
    await session.commit()

    await seed_agents(session, BUILTIN_AGENTS)
    await session.commit()

    refreshed = await session.get(AgentRecord, "coding-agent")
    assert refreshed is not None
    # Startup seeding must not silently re-enable an agent an operator turned off.
    assert refreshed.enabled is False
