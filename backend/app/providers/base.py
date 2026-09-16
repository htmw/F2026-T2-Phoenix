"""The provider abstraction.

Everything above this layer talks to ``LLMProvider``; nothing above it imports a vendor
SDK, knows a vendor's error codes, or parses a vendor's response shape. Adapters absorb
those differences and map failures onto the shared ``ErrorKind`` taxonomy so retry
policy is written once instead of per provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.domain.enums import ErrorKind, ModelTrait
from app.schemas.execution import TokenUsage


class ProviderError(Exception):
    """A provider failure, classified for retry decisions.

    Adapters raise this instead of leaking ``httpx``, ``openai``, or ``anthropic``
    exceptions, which is what keeps vendor concerns out of the executor.
    """

    def __init__(
        self,
        kind: ErrorKind,
        message: str,
        *,
        provider: str,
        retryable: bool | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self._retryable = retryable

    @property
    def is_retryable(self) -> bool:
        return self.kind.is_retryable if self._retryable is None else self._retryable


class ProviderConfigurationError(ProviderError):
    """Raised when a provider cannot be used at all, e.g. a missing credential."""

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(ErrorKind.AUTHENTICATION, message, provider=provider, retryable=False)


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """What a model offers and what it costs.

    Pricing is per million tokens because that is how providers publish it; converting
    at the boundary avoids scattered arithmetic and rounding drift.
    """

    id: str
    provider: str
    model_name: str
    traits: frozenset[ModelTrait]
    context_tokens: int
    max_output_tokens: int
    input_cost_per_million: float
    output_cost_per_million: float
    typical_latency_ms: int = 2_000

    def cost_for(self, usage: TokenUsage) -> float:
        return (
            usage.input_tokens * self.input_cost_per_million
            + usage.output_tokens * self.output_cost_per_million
        ) / 1_000_000

    def supports(self, traits: frozenset[ModelTrait]) -> bool:
        return traits <= self.traits


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """A provider-neutral request.

    ``response_schema`` carries the agent's JSON Schema so adapters can use native
    structured-output support where it exists and fall back to prompt instructions where
    it does not — without the caller needing to know which is which.
    """

    model: ModelSpec
    system_prompt: str
    user_prompt: str
    max_output_tokens: int = 4_096
    temperature: float = 0.2
    response_schema: dict[str, object] | None = None
    timeout_seconds: float = 120.0


@dataclass(frozen=True, slots=True)
class CompletionResponse:
    text: str
    usage: TokenUsage
    model: str
    provider: str
    finish_reason: str | None = None
    latency_ms: float = 0.0
    raw_metadata: dict[str, object] = field(default_factory=dict)

    def cost(self, model: ModelSpec) -> float:
        return model.cost_for(self.usage)


class LLMProvider(ABC):
    """Interface every provider adapter implements."""

    #: Stable identifier used in configuration, routing, and cost records.
    name: str

    @abstractmethod
    async def generate(self, request: CompletionRequest) -> CompletionResponse:
        """Produce a single completion."""

    @abstractmethod
    def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Yield completion text incrementally.

        Not a coroutine: implementations are async generators, so the method returns the
        iterator directly and is consumed with ``async for``.
        """

    @abstractmethod
    def estimate_cost(self, request: CompletionRequest) -> float:
        """Estimate the cost of a request before it is sent.

        Used to enforce an agent's cost ceiling *before* spending money, so the estimate
        must be conservative rather than optimistic.
        """

    @abstractmethod
    def validate_configuration(self) -> None:
        """Raise ``ProviderConfigurationError`` if this provider cannot be used."""

    @abstractmethod
    def get_model_capabilities(self) -> tuple[ModelSpec, ...]:
        """Models this provider offers, with traits and pricing."""

    def is_configured(self) -> bool:
        try:
            self.validate_configuration()
        except ProviderConfigurationError:
            return False
        return True


def estimate_tokens(text: str) -> int:
    """Rough token estimate used for pre-flight cost checks.

    Deliberately crude: about four characters per token, rounded up. Exact counting
    needs a per-model tokeniser, and the only decision this feeds is "might this exceed
    the budget", where over-estimating is the safe direction.
    """
    return max(1, (len(text) + 3) // 4)
