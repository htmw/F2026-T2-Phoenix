"""An in-memory provider used by tests and local development.

This exists so the entire orchestration engine can be exercised — including retries,
failures, and malformed output — without a network call or a cent of spend. It is a
first-class adapter, not a production vendor: the catalogue API labels it Demo Mode and
production never registers it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Mapping

from app.domain.enums import ErrorKind, ModelTrait
from app.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    ModelSpec,
    ProviderError,
    estimate_tokens,
)
from app.schemas.execution import TokenUsage

# Internal ids keep the ``fake:`` namespace for hermetic tests. They must never be
# presented as real vendor models in production UI (see ProviderStatusView.demo).
FAKE_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        id="fake:reasoner",
        provider="fake",
        model_name="fake-reasoner",
        traits=frozenset({ModelTrait.REASONING, ModelTrait.CODING, ModelTrait.STRUCTURED_OUTPUT}),
        context_tokens=128_000,
        max_output_tokens=16_384,
        input_cost_per_million=1.0,
        output_cost_per_million=3.0,
        typical_latency_ms=800,
    ),
    ModelSpec(
        id="fake:cheap",
        provider="fake",
        model_name="fake-cheap",
        traits=frozenset({ModelTrait.FAST, ModelTrait.CHEAP, ModelTrait.STRUCTURED_OUTPUT}),
        context_tokens=32_000,
        max_output_tokens=4_096,
        input_cost_per_million=0.05,
        output_cost_per_million=0.15,
        typical_latency_ms=200,
    ),
)

# A response may be a literal string or a callable that inspects the request.
ResponseFactory = Callable[[CompletionRequest], str]


class FakeProvider(LLMProvider):
    """A scripted provider.

    Responses are queued per model id, or a default is used. Failures can be scripted
    the same way, which is how provider-failure and retry paths get deterministic tests.
    """

    name = "fake"

    def __init__(
        self,
        *,
        default_response: str | ResponseFactory | None = None,
        models: tuple[ModelSpec, ...] = FAKE_MODELS,
        configured: bool = True,
    ) -> None:
        self._models = models
        self._configured = configured
        self._default = default_response
        self._queued: dict[str, list[str | ResponseFactory | ProviderError]] = defaultdict(list)
        self._global_queue: list[str | ResponseFactory | ProviderError] = []
        #: Every request received, in order. Tests assert on what was actually sent.
        self.requests: list[CompletionRequest] = []

    # ---- scripting helpers -------------------------------------------------

    def queue_response(
        self, response: str | ResponseFactory, *, model_id: str | None = None
    ) -> None:
        if model_id is None:
            self._global_queue.append(response)
        else:
            self._queued[model_id].append(response)

    def queue_json(self, payload: Mapping[str, object], *, model_id: str | None = None) -> None:
        """Queue a JSON response. Accepts any mapping so callers need no annotations."""
        self.queue_response(json.dumps(payload), model_id=model_id)

    def queue_failure(
        self,
        kind: ErrorKind = ErrorKind.PROVIDER_UNAVAILABLE,
        message: str = "scripted failure",
        *,
        model_id: str | None = None,
    ) -> None:
        error = ProviderError(kind, message, provider=self.name)
        if model_id is None:
            self._global_queue.append(error)
        else:
            self._queued[model_id].append(error)

    # ---- LLMProvider -------------------------------------------------------

    async def generate(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        next_item = self._take(request)

        if isinstance(next_item, ProviderError):
            raise next_item

        text = next_item(request) if callable(next_item) else next_item
        usage = TokenUsage(
            input_tokens=estimate_tokens(request.system_prompt + request.user_prompt),
            output_tokens=estimate_tokens(text),
        )
        return CompletionResponse(
            text=text,
            usage=usage,
            model=request.model.id,
            provider=self.name,
            finish_reason="stop",
            latency_ms=float(request.model.typical_latency_ms),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        response = await self.generate(request)
        for chunk in response.text.split(" "):
            yield f"{chunk} "

    def estimate_cost(self, request: CompletionRequest) -> float:
        prompt_tokens = estimate_tokens(request.system_prompt + request.user_prompt)
        # Assume the model emits its full allowance: the estimate guards a budget, so
        # under-estimating would let a call through that cannot be afforded.
        return request.model.cost_for(
            TokenUsage(input_tokens=prompt_tokens, output_tokens=request.max_output_tokens)
        )

    def validate_configuration(self) -> None:
        if not self._configured:
            from app.providers.base import ProviderConfigurationError

            raise ProviderConfigurationError(
                "fake provider marked unconfigured", provider=self.name
            )

    def get_model_capabilities(self) -> tuple[ModelSpec, ...]:
        return self._models

    # ---- internals ---------------------------------------------------------

    def _take(self, request: CompletionRequest) -> str | ResponseFactory | ProviderError:
        if queued := self._queued.get(request.model.id):
            return queued.pop(0)
        if self._global_queue:
            return self._global_queue.pop(0)
        if self._default is not None:
            return self._default
        # With no script, echo a schema-shaped stub so happy-path tests that do not
        # care about content still get valid output.
        return json.dumps(_stub_for_schema(request.response_schema))


def _stub_for_schema(schema: dict[str, object] | None) -> dict[str, object]:
    """Build a minimal object satisfying a JSON Schema's required fields."""
    if not schema:
        return {"result": "ok"}

    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict):
        return {"result": "ok"}

    wanted = required if isinstance(required, list) else list(properties)
    stub: dict[str, object] = {}
    for key in wanted:
        definition = properties.get(key, {})
        stub[str(key)] = _stub_for_property(definition if isinstance(definition, dict) else {})
    return stub


def _stub_for_property(definition: dict[str, object]) -> object:
    match definition.get("type"):
        case "array":
            return []
        case "boolean":
            return True
        case "integer":
            return 0
        case "number":
            return 0.0
        case "object":
            return {}
        case _:
            enum = definition.get("enum")
            if isinstance(enum, list) and enum:
                return enum[0]
            return "stub"
