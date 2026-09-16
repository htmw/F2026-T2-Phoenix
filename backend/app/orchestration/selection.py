"""Turning required capabilities into a set of agents, with reasons.

Selection answers two questions the user is entitled to ask: why did this agent run, and
why did that one not? Both answers are recorded, so "only the necessary agents ran" is
an auditable claim rather than a promise.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.registry import AgentNotFoundError, AgentRegistry
from app.core.logging import get_logger
from app.domain.enums import Capability
from app.schemas.agent import AgentDefinition

logger = get_logger(__name__)


class NoAgentForCapabilityError(RuntimeError):
    """Raised when nothing in the registry covers a required capability."""

    def __init__(self, uncovered: set[Capability]) -> None:
        self.uncovered = uncovered
        names = ", ".join(sorted(capability.value for capability in uncovered))
        super().__init__(f"no enabled agent provides: {names}")


class UnknownAgentsError(RuntimeError):
    """Raised when the operator names agents that are missing or disabled."""

    def __init__(self, agent_ids: list[str]) -> None:
        self.agent_ids = agent_ids
        names = ", ".join(agent_ids)
        super().__init__(f"unknown or disabled agents: {names}")


@dataclass(frozen=True, slots=True)
class SelectionResult:
    #: Chosen agents, each with the capabilities it was chosen to satisfy.
    chosen: dict[str, frozenset[Capability]]
    definitions: dict[str, AgentDefinition]
    excluded: dict[str, str]

    @property
    def agent_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.chosen))


class AgentSelector:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    async def select(
        self,
        required: frozenset[Capability],
        *,
        agent_ids: frozenset[str] | None = None,
    ) -> SelectionResult:
        """Choose agents covering every required capability.

        When ``agent_ids`` is set, that exact roster runs: each agent is assigned the
        intersection of its capabilities with what the request needs (or its full set if
        the request does not mention them, because the operator forced inclusion).
        """
        if agent_ids is not None:
            return await self._select_exact(required, agent_ids)
        return await self._select_minimal(required)

    async def _select_exact(
        self, required: frozenset[Capability], agent_ids: frozenset[str]
    ) -> SelectionResult:
        definitions: dict[str, AgentDefinition] = {}
        chosen: dict[str, frozenset[Capability]] = {}
        unknown: list[str] = []
        for agent_id in sorted(agent_ids):
            try:
                agent = await self._registry.get(agent_id)
            except AgentNotFoundError:
                unknown.append(agent_id)
                continue
            if not agent.enabled:
                unknown.append(agent_id)
                continue
            definitions[agent_id] = agent
            overlap = agent.capabilities & required
            chosen[agent_id] = frozenset(overlap) if overlap else frozenset(agent.capabilities)

        if unknown:
            raise UnknownAgentsError(unknown)

        excluded = await self._explain_exclusions(set(chosen), required, forced=True)
        logger.info(
            "agents_selected",
            selected=sorted(chosen),
            excluded=sorted(excluded),
            required=sorted(capability.value for capability in required),
            mode="exact",
        )
        return SelectionResult(chosen=chosen, definitions=definitions, excluded=excluded)

    async def _select_minimal(self, required: frozenset[Capability]) -> SelectionResult:
        """Choose a minimal set of agents covering every required capability.

        An agent covering several required capabilities is preferred over several
        agents covering one each: fewer agents means fewer calls, less hand-off, and
        less cost for the same coverage.
        """
        coverage = await self._registry.find_by_capabilities(set(required))

        uncovered = {capability for capability, agents in coverage.items() if not agents}
        if uncovered:
            # Better to refuse than to silently answer a different question than asked.
            raise NoAgentForCapabilityError(uncovered)

        by_agent: dict[str, set[Capability]] = {}
        definitions: dict[str, AgentDefinition] = {}
        for capability, agents in coverage.items():
            for agent in agents:
                by_agent.setdefault(agent.id, set()).add(capability)
                definitions[agent.id] = agent

        chosen: dict[str, frozenset[Capability]] = {}
        remaining = set(required)
        while remaining:
            # Greedy set cover: most remaining coverage first, cheapest as a tie-break,
            # then id for determinism. Optimal cover is NP-hard and the registry is
            # small, so a predictable greedy choice is the right trade.
            best = max(
                by_agent,
                key=lambda agent_id: (
                    len(by_agent[agent_id] & remaining),
                    -definitions[agent_id].limits.max_cost_usd,
                    # Reverse id so `max` prefers the alphabetically first agent.
                    tuple(-ord(character) for character in agent_id),
                ),
            )
            covered = by_agent[best] & remaining
            if not covered:
                break
            chosen[best] = frozenset(covered)
            remaining -= covered
            del by_agent[best]

        excluded = await self._explain_exclusions(set(chosen), required, forced=False)

        logger.info(
            "agents_selected",
            selected=sorted(chosen),
            excluded=sorted(excluded),
            required=sorted(capability.value for capability in required),
            mode="auto",
        )
        return SelectionResult(chosen=chosen, definitions=definitions, excluded=excluded)

    async def _explain_exclusions(
        self,
        chosen: set[str],
        required: frozenset[Capability],
        *,
        forced: bool,
    ) -> dict[str, str]:
        excluded: dict[str, str] = {}
        for agent in await self._registry.list_all():
            if agent.id in chosen:
                continue
            if forced:
                excluded[agent.id] = "not included in the operator's agent selection"
                continue
            overlap = agent.capabilities & required
            excluded[agent.id] = (
                "its capabilities were already covered by a selected agent"
                if overlap
                else "none of its capabilities are required by this request"
            )
        return excluded
