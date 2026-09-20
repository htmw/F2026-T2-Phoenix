"""Contracts for a generatively designed agent team (Level 3).

A team is designed per request by the meta-planner and then compiled into ephemeral
``AgentDefinition``s and a ``WorkflowPlan``. These types are the validated boundary
between the model's free-form design and the strongly-typed graph the engine runs.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TeamAgentSpec(BaseModel):
    """One specialist the meta-planner proposes."""

    model_config = ConfigDict(frozen=True)

    #: Human-readable role, e.g. "Market Sizing Analyst". Also the display name.
    role: str = Field(min_length=1, max_length=80)
    #: What this specialist should produce, in one or two sentences.
    objective: str = Field(min_length=1, max_length=2_000)
    #: Roles this one depends on (must match other agents' ``role`` values).
    depends_on: tuple[str, ...] = ()
    #: Exactly one agent is the synthesizer that writes the final deliverable.
    is_synthesizer: bool = False


class TeamSpec(BaseModel):
    """A validated team design: a small set of specialists plus one synthesizer."""

    model_config = ConfigDict(frozen=True)

    domain: str = Field(min_length=1, max_length=80)
    reasoning: str = Field(default="", max_length=2_000)
    agents: tuple[TeamAgentSpec, ...] = Field(min_length=1)

    @property
    def synthesizer(self) -> TeamAgentSpec | None:
        return next((agent for agent in self.agents if agent.is_synthesizer), None)
