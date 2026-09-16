"""Agent metadata contracts.

An agent is *data*: a declaration of what it can do, what it accepts, what it returns,
and the limits it runs under. Nothing here describes how to execute it, which is what
allows a new agent to be registered without changes to the orchestrator or executor.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import Capability, ModelTrait


class RetryPolicy(BaseModel):
    """How many times to retry an agent and how long to wait between attempts."""

    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=2, ge=1, le=10)
    initial_backoff_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    max_backoff_seconds: float = Field(default=30.0, ge=0.0, le=300.0)

    def backoff_for_attempt(self, attempt: int) -> float:
        """Delay before ``attempt`` (1-based); attempt 1 is the initial try, so 0."""
        if attempt <= 1:
            return 0.0
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 2))
        return min(delay, self.max_backoff_seconds)


class ModelPreference(BaseModel):
    """What kind of model an agent wants, in priority order.

    Agents declare *traits* rather than model ids so routing can satisfy them from
    whichever provider is configured, available, and affordable. An explicit
    ``preferred_model`` is an optional Fixed binding (operator or per-run override) —
    never part of the agent's role definition.
    """

    model_config = ConfigDict(frozen=True)

    required_traits: tuple[ModelTrait, ...] = ()
    preferred_traits: tuple[ModelTrait, ...] = ()
    preferred_model: str | None = None
    preferred_provider: str | None = None
    min_context_tokens: int = Field(default=8_000, ge=1_000)
    max_output_tokens: int = Field(default=4_096, ge=256, le=200_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    @property
    def model_strategy(self) -> str:
        """``fixed`` when a binding is set; otherwise ``auto`` (router chooses)."""
        return "fixed" if self.preferred_model else "auto"


class AgentLimits(BaseModel):
    """Guardrails enforced by the executor before and during a call."""

    model_config = ConfigDict(frozen=True)

    timeout_seconds: float = Field(default=120.0, gt=0, le=1_800)
    max_cost_usd: float = Field(default=0.50, gt=0, le=100.0)


class AgentDefinition(BaseModel):
    """A registered agent.

    ``output_schema`` is a JSON Schema document. Agent output is validated against it
    before it can influence control flow, which is the boundary where untrusted model
    output becomes trusted domain data.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    capabilities: frozenset[Capability] = Field(min_length=1)
    instructions: str = Field(min_length=1)
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_schema: dict[str, object]
    model_preference: ModelPreference = ModelPreference()
    tools: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    limits: AgentLimits = AgentLimits()
    retry_policy: RetryPolicy = RetryPolicy()
    enabled: bool = True

    @model_validator(mode="after")
    def _require_object_output_schema(self) -> AgentDefinition:
        # Agents hand structured records to other agents, so a bare string or array at
        # the top level would break field-level input construction downstream.
        if self.output_schema.get("type") != "object":
            raise ValueError(f"agent {self.id}: output_schema must describe an object")
        return self

    def provides(self, capability: Capability) -> bool:
        return capability in self.capabilities


class AgentModelBinding(BaseModel):
    """Operator Fixed binding for an agent. ``preferred_model`` null clears to Auto."""

    model_config = ConfigDict(frozen=True)

    preferred_model: str | None = Field(default=None, max_length=128)


class AgentSummary(BaseModel):
    """Public view of an agent. Deliberately excludes prompt instructions."""

    id: str
    name: str
    description: str
    version: str
    capabilities: list[Capability]
    tools: list[str]
    permissions: list[str]
    #: ``auto`` = router selects any compatible connected model; ``fixed`` = binding set.
    model_strategy: str = "auto"
    preferred_provider: str | None = None
    preferred_model: str | None = None
    timeout_seconds: float
    max_cost_usd: float
    max_attempts: int
    enabled: bool

    @classmethod
    def from_definition(cls, definition: AgentDefinition) -> AgentSummary:
        preference = definition.model_preference
        return cls(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            version=definition.version,
            capabilities=sorted(definition.capabilities),
            tools=list(definition.tools),
            permissions=list(definition.permissions),
            model_strategy=preference.model_strategy,
            preferred_provider=preference.preferred_provider,
            preferred_model=preference.preferred_model,
            timeout_seconds=definition.limits.timeout_seconds,
            max_cost_usd=definition.limits.max_cost_usd,
            max_attempts=definition.retry_policy.max_attempts,
            enabled=definition.enabled,
        )
