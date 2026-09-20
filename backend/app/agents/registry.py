"""The agent registry.

The orchestrator depends on the ``AgentRegistry`` protocol, never on a concrete
implementation, and it looks agents up by *capability*. That is the mechanism behind the
"add an agent without touching the engine" requirement: registration is data entry, and
selection is a query.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Capability
from app.models.agent import AgentCapabilityRecord, AgentRecord
from app.schemas.agent import (
    AgentDefinition,
    AgentLimits,
    ModelPreference,
    RetryPolicy,
)


class DuplicateAgentError(ValueError):
    """Raised when an agent id is registered twice."""


class AgentNotFoundError(KeyError):
    """Raised when an agent id is not registered."""


@runtime_checkable
class AgentRegistry(Protocol):
    """Read interface used by the orchestrator."""

    async def get(self, agent_id: str) -> AgentDefinition: ...

    async def list_all(self, *, include_disabled: bool = False) -> list[AgentDefinition]: ...

    async def find_by_capability(self, capability: Capability) -> list[AgentDefinition]: ...

    async def find_by_capabilities(
        self, capabilities: set[Capability]
    ) -> dict[Capability, list[AgentDefinition]]: ...


class InMemoryAgentRegistry:
    """Registry backed by a dict.

    Used by tests and by any code path that must not touch the database. It is the same
    interface as the database registry, so a test that registers a brand-new agent
    proves the engine needs no modification to use it.
    """

    def __init__(self, definitions: list[AgentDefinition] | None = None) -> None:
        self._agents: dict[str, AgentDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: AgentDefinition) -> None:
        if definition.id in self._agents:
            raise DuplicateAgentError(f"agent '{definition.id}' is already registered")
        self._agents[definition.id] = definition

    async def get(self, agent_id: str) -> AgentDefinition:
        try:
            return self._agents[agent_id]
        except KeyError:
            raise AgentNotFoundError(f"agent '{agent_id}' is not registered") from None

    async def list_all(self, *, include_disabled: bool = False) -> list[AgentDefinition]:
        return sorted(
            (a for a in self._agents.values() if include_disabled or a.enabled),
            key=lambda agent: agent.id,
        )

    async def find_by_capability(self, capability: Capability) -> list[AgentDefinition]:
        return [agent for agent in await self.list_all() if agent.provides(capability)]

    async def find_by_capabilities(
        self, capabilities: set[Capability]
    ) -> dict[Capability, list[AgentDefinition]]:
        return {
            capability: await self.find_by_capability(capability) for capability in capabilities
        }


class OverlayAgentRegistry:
    """A base registry with a per-run overlay of ephemeral agents.

    Generative teams are designed on the fly and must not be persisted into the shared
    registry: they are specific to one run, and writing them as rows would pollute
    selection and the office roster. ``get`` resolves the overlay first, so the engine
    can execute a generated agent by id, while capability queries and listings delegate
    to the base — an ephemeral agent is run because the plan names it, never selected.
    """

    def __init__(self, base: AgentRegistry, overlay: dict[str, AgentDefinition]) -> None:
        self._base = base
        self._overlay = dict(overlay)

    async def get(self, agent_id: str) -> AgentDefinition:
        if agent_id in self._overlay:
            return self._overlay[agent_id]
        return await self._base.get(agent_id)

    async def list_all(self, *, include_disabled: bool = False) -> list[AgentDefinition]:
        return await self._base.list_all(include_disabled=include_disabled)

    async def find_by_capability(self, capability: Capability) -> list[AgentDefinition]:
        return await self._base.find_by_capability(capability)

    async def find_by_capabilities(
        self, capabilities: set[Capability]
    ) -> dict[Capability, list[AgentDefinition]]:
        return await self._base.find_by_capabilities(capabilities)


class DatabaseAgentRegistry:
    """Registry backed by the ``agents`` table.

    Capability lookups are a join on an indexed column rather than a scan over JSON, so
    selection stays cheap as the registry grows.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, agent_id: str) -> AgentDefinition:
        record = await self._session.get(AgentRecord, agent_id)
        if record is None:
            raise AgentNotFoundError(f"agent '{agent_id}' is not registered")
        return record_to_definition(record)

    async def list_all(self, *, include_disabled: bool = False) -> list[AgentDefinition]:
        statement = select(AgentRecord).order_by(AgentRecord.id)
        if not include_disabled:
            statement = statement.where(AgentRecord.enabled.is_(True))
        result = await self._session.execute(statement)
        return [record_to_definition(record) for record in result.scalars()]

    async def find_by_capability(self, capability: Capability) -> list[AgentDefinition]:
        statement = (
            select(AgentRecord)
            .join(AgentCapabilityRecord)
            .where(
                AgentCapabilityRecord.capability == capability.value,
                AgentRecord.enabled.is_(True),
            )
            .order_by(AgentRecord.id)
        )
        result = await self._session.execute(statement)
        return [record_to_definition(record) for record in result.scalars().unique()]

    async def find_by_capabilities(
        self, capabilities: set[Capability]
    ) -> dict[Capability, list[AgentDefinition]]:
        if not capabilities:
            return {}
        wanted = {capability.value for capability in capabilities}
        statement = (
            select(AgentRecord, AgentCapabilityRecord.capability)
            .join(AgentCapabilityRecord)
            .where(
                AgentCapabilityRecord.capability.in_(wanted),
                AgentRecord.enabled.is_(True),
            )
            .order_by(AgentRecord.id)
        )
        result = await self._session.execute(statement)

        # One query for every requested capability, grouped in memory: agent selection
        # runs on every submitted task, so a query per capability would not scale.
        grouped: dict[Capability, list[AgentDefinition]] = {c: [] for c in capabilities}
        for record, capability_value in result.all():
            grouped[Capability(capability_value)].append(record_to_definition(record))
        return grouped

    async def set_model_binding(
        self, agent_id: str, preferred_model: str | None
    ) -> AgentDefinition:
        """Set or clear an operator Fixed binding. Does not change role traits."""
        record = await self._session.get(AgentRecord, agent_id)
        if record is None:
            raise AgentNotFoundError(f"agent '{agent_id}' is not registered")
        preference = dict(record.model_preference or {})
        if preferred_model:
            preference["preferred_model"] = preferred_model
            preference["preferred_provider"] = (
                preferred_model.split(":", 1)[0] if ":" in preferred_model else None
            )
        else:
            preference.pop("preferred_model", None)
            preference.pop("preferred_provider", None)
        record.model_preference = preference
        await self._session.flush()
        return record_to_definition(record)


def record_to_definition(record: AgentRecord) -> AgentDefinition:
    """Rehydrate a stored row into a validated definition.

    Stored JSON is treated as untrusted: it was written by an earlier schema version or
    by an operator, so Pydantic validates it on the way out rather than assuming it is
    well-formed.
    """
    return AgentDefinition(
        id=record.id,
        name=record.name,
        description=record.description,
        version=record.version,
        capabilities=frozenset(Capability(c.capability) for c in record.capabilities),
        instructions=record.instructions,
        input_schema=dict(record.input_schema),
        output_schema=dict(record.output_schema),
        model_preference=ModelPreference.model_validate(record.model_preference),
        tools=tuple(record.tools),
        permissions=tuple(record.permissions),
        limits=AgentLimits(
            timeout_seconds=record.timeout_seconds,
            max_cost_usd=record.max_cost_usd,
        ),
        retry_policy=RetryPolicy.model_validate(record.retry_policy),
        enabled=record.enabled,
    )
