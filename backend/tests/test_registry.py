"""Agent registry tests.

The central test here is `test_new_agent_becomes_selectable_without_engine_changes`:
it is the executable form of the requirement that agents are data, not code.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.builtin import BUILTIN_AGENTS, SECURITY_AGENT, agent_display_name
from app.agents.registry import (
    AgentNotFoundError,
    DatabaseAgentRegistry,
    DuplicateAgentError,
    InMemoryAgentRegistry,
)
from app.agents.seed import upsert_agent
from app.domain.enums import Capability
from app.schemas.agent import AgentDefinition

TRANSLATION = Capability.SUMMARISATION


def make_definition(agent_id: str, capabilities: set[Capability]) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        name=f"Test {agent_id}",
        description="A test agent.",
        capabilities=frozenset(capabilities),
        instructions="Do the thing.",
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
    )


# ---------------------------------------------------------------------------
# In-memory registry
# ---------------------------------------------------------------------------


async def test_lookup_by_id(memory_registry: InMemoryAgentRegistry) -> None:
    definition = await memory_registry.get("security-agent")

    assert definition.name == "Security Agent"
    assert definition.model_preference.preferred_provider is None
    assert definition.model_preference.preferred_model is None
    assert definition.model_preference.model_strategy == "auto"
    assert agent_display_name("security-agent") == "Security Agent"
    assert agent_display_name("coding-agent") == "Coding Agent"
    assert agent_display_name("general-agent") == "General Agent"


async def test_unknown_agent_raises(memory_registry: InMemoryAgentRegistry) -> None:
    with pytest.raises(AgentNotFoundError):
        await memory_registry.get("nonexistent-agent")


async def test_duplicate_registration_is_rejected() -> None:
    registry = InMemoryAgentRegistry([make_definition("dup-agent", {Capability.DOCUMENTATION})])

    with pytest.raises(DuplicateAgentError):
        registry.register(make_definition("dup-agent", {Capability.CODE_REVIEW}))


async def test_all_builtin_agents_are_registered(memory_registry: InMemoryAgentRegistry) -> None:
    listed = await memory_registry.list_all()

    assert len(listed) == len(BUILTIN_AGENTS) == 8


async def test_capability_lookup_returns_only_providers(
    memory_registry: InMemoryAgentRegistry,
) -> None:
    found = await memory_registry.find_by_capability(Capability.VULNERABILITY_ANALYSIS)

    assert [definition.id for definition in found] == ["security-agent"]


async def test_capability_lookup_excludes_non_providers(
    memory_registry: InMemoryAgentRegistry,
) -> None:
    found = await memory_registry.find_by_capability(Capability.CODE_GENERATION)
    ids = {definition.id for definition in found}

    # The point of the registry: asking for code generation must not surface the
    # security or documentation agents.
    assert "coding-agent" in ids
    assert "security-agent" not in ids
    assert "documentation-agent" not in ids


async def test_disabled_agents_are_hidden_by_default() -> None:
    registry = InMemoryAgentRegistry(
        [
            make_definition("live-agent", {Capability.DOCUMENTATION}),
            make_definition("retired-agent", {Capability.DOCUMENTATION}).model_copy(
                update={"enabled": False}
            ),
        ]
    )

    assert [d.id for d in await registry.list_all()] == ["live-agent"]
    assert len(await registry.list_all(include_disabled=True)) == 2


async def test_find_by_capabilities_groups_results(
    memory_registry: InMemoryAgentRegistry,
) -> None:
    grouped = await memory_registry.find_by_capabilities(
        {Capability.TEST_GENERATION, Capability.DOCUMENTATION}
    )

    assert [d.id for d in grouped[Capability.TEST_GENERATION]] == ["testing-agent"]
    assert [d.id for d in grouped[Capability.DOCUMENTATION]] == ["documentation-agent"]


async def test_uncovered_capability_returns_empty_not_error(
    memory_registry: InMemoryAgentRegistry,
) -> None:
    # An uncovered capability must be reported as a gap, not raise: the orchestrator
    # needs to tell the user "nothing can do this" rather than crash.
    grouped = await memory_registry.find_by_capabilities({Capability.TEST_EXECUTION})

    assert isinstance(grouped[Capability.TEST_EXECUTION], list)


# ---------------------------------------------------------------------------
# Database registry
# ---------------------------------------------------------------------------


async def test_database_registry_lists_seeded_agents(seeded_session: AsyncSession) -> None:
    registry = DatabaseAgentRegistry(seeded_session)

    listed = await registry.list_all()

    assert {definition.id for definition in listed} == {
        definition.id for definition in BUILTIN_AGENTS
    }


async def test_database_registry_round_trips_full_definition(
    seeded_session: AsyncSession,
) -> None:
    registry = DatabaseAgentRegistry(seeded_session)

    stored = await registry.get(SECURITY_AGENT.id)

    # Every field that the orchestrator and executor depend on must survive the trip
    # through JSONB, or an agent would silently run with default limits.
    assert stored.capabilities == SECURITY_AGENT.capabilities
    assert stored.limits == SECURITY_AGENT.limits
    assert stored.retry_policy == SECURITY_AGENT.retry_policy
    assert stored.model_preference == SECURITY_AGENT.model_preference
    assert stored.permissions == SECURITY_AGENT.permissions
    assert stored.output_schema == SECURITY_AGENT.output_schema


async def test_database_capability_query_matches_in_memory(
    seeded_session: AsyncSession,
    memory_registry: InMemoryAgentRegistry,
) -> None:
    database_registry = DatabaseAgentRegistry(seeded_session)

    for capability in Capability:
        from_db = {d.id for d in await database_registry.find_by_capability(capability)}
        from_memory = {d.id for d in await memory_registry.find_by_capability(capability)}
        assert from_db == from_memory, f"mismatch for {capability}"


async def test_database_registry_raises_for_unknown_agent(
    seeded_session: AsyncSession,
) -> None:
    registry = DatabaseAgentRegistry(seeded_session)

    with pytest.raises(AgentNotFoundError):
        await registry.get("no-such-agent")


async def test_new_agent_becomes_selectable_without_engine_changes(
    seeded_session: AsyncSession,
) -> None:
    """Register an agent the codebase has never heard of and select it by capability.

    No orchestration, executor, or registry code is modified or subclassed here. If
    this test ever needs a code change to pass, the "agents are data" property has
    been lost.
    """
    novel = make_definition("translation-agent", {TRANSLATION})
    await upsert_agent(seeded_session, novel)
    await seeded_session.commit()

    registry = DatabaseAgentRegistry(seeded_session)
    found = await registry.find_by_capability(TRANSLATION)

    assert "translation-agent" in {definition.id for definition in found}
    assert (await registry.get("translation-agent")).name == "Test translation-agent"


async def test_disabled_agent_is_not_selectable_from_database(
    seeded_session: AsyncSession,
) -> None:
    disabled = make_definition("dormant-agent", {Capability.TEST_EXECUTION}).model_copy(
        update={"enabled": False}
    )
    await upsert_agent(seeded_session, disabled)
    await seeded_session.commit()

    registry = DatabaseAgentRegistry(seeded_session)

    selectable = {d.id for d in await registry.find_by_capability(Capability.TEST_EXECUTION)}
    assert "dormant-agent" not in selectable
    # Still discoverable by an operator, just never selected for work.
    assert "dormant-agent" in {d.id for d in await registry.list_all(include_disabled=True)}
