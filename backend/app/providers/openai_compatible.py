"""Adapter for providers exposing an OpenAI-compatible chat-completions API.

OpenAI, DeepSeek, xAI, Mistral, OpenRouter, and Gemini (via Google's OpenAI-compatible
endpoint) share one request shape and differ only in base URL, credential, and catalogue.
Anthropic stays in ``anthropic.py`` because the Messages API is a different protocol.

Vendor HTTP details, status codes, and response parsing stop here. Callers see
``CompletionResponse`` or ``ProviderError``.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

import httpx

from app.core.logging import get_logger
from app.domain.enums import ErrorKind, ModelTrait
from app.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    ModelSpec,
    ProviderConfigurationError,
    ProviderError,
    estimate_tokens,
)
from app.schemas.execution import TokenUsage

logger = get_logger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """Base adapter for the OpenAI chat-completions protocol."""

    name = "openai-compatible"
    base_url = "https://api.openai.com/v1"
    models: tuple[ModelSpec, ...] = ()

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or self.base_url).rstrip("/")
        # An injected client is how tests exercise this adapter against a transport stub
        # instead of the network.
        self._client = client

    # ---- LLMProvider -------------------------------------------------------

    def validate_configuration(self) -> None:
        if not self._api_key:
            raise ProviderConfigurationError(
                f"{self.name}: no API key configured", provider=self.name
            )
        if not self.models:
            raise ProviderConfigurationError(f"{self.name}: no models declared", provider=self.name)

    def get_model_capabilities(self) -> tuple[ModelSpec, ...]:
        return self.models

    def estimate_cost(self, request: CompletionRequest) -> float:
        prompt_tokens = estimate_tokens(request.system_prompt + request.user_prompt)
        # Assume maximum output: this estimate guards a spend limit, so the error must
        # be on the expensive side.
        return request.model.cost_for(
            TokenUsage(input_tokens=prompt_tokens, output_tokens=request.max_output_tokens)
        )

    async def generate(self, request: CompletionRequest) -> CompletionResponse:
        self.validate_configuration()
        payload = self._build_payload(request, stream=False)
        started = time.perf_counter()

        client = self._client or httpx.AsyncClient(timeout=request.timeout_seconds)
        owns_client = self._client is None
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                ErrorKind.TIMEOUT, f"{self.name}: request timed out", provider=self.name
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                ErrorKind.PROVIDER_UNAVAILABLE,
                f"{self.name}: transport error",
                provider=self.name,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code >= 400:
            raise self._map_error(response)

        latency_ms = (time.perf_counter() - started) * 1000
        return self._parse_response(response.json(), request, latency_ms)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        self.validate_configuration()
        payload = self._build_payload(request, stream=True)

        client = self._client or httpx.AsyncClient(timeout=request.timeout_seconds)
        owns_client = self._client is None
        try:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=request.timeout_seconds,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise self._map_error(response)

                async for line in response.aiter_lines():
                    if chunk := self._parse_stream_line(line):
                        yield chunk
        except httpx.TimeoutException as exc:
            raise ProviderError(
                ErrorKind.TIMEOUT, f"{self.name}: stream timed out", provider=self.name
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    # ---- internals ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def list_remote_model_ids(self, *, timeout_seconds: float = 30.0) -> list[str]:
        """Discover model ids from the provider's ``GET /models`` endpoint when available."""
        self.validate_configuration()
        client = self._client or httpx.AsyncClient(timeout=timeout_seconds)
        owns_client = self._client is None
        try:
            response = await client.get(
                f"{self._base_url}/models",
                headers=self._headers(),
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                ErrorKind.TIMEOUT, f"{self.name}: model list timed out", provider=self.name
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                ErrorKind.PROVIDER_UNAVAILABLE,
                f"{self.name}: transport error listing models",
                provider=self.name,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code >= 400:
            raise self._map_error(response)

        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []
        ids: list[str] = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.append(item["id"])
        return ids

    def _build_payload(self, request: CompletionRequest, *, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model.model_name,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": min(request.max_output_tokens, request.model.max_output_tokens),
            "temperature": request.temperature,
        }
        if stream:
            payload["stream"] = True
        if request.response_schema is not None and ModelTrait.STRUCTURED_OUTPUT in (
            request.model.traits
        ):
            # Native JSON mode where the model supports it; the executor still validates
            # the result, because "JSON mode" guarantees syntax, not schema conformance.
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _map_error(self, response: httpx.Response) -> ProviderError:
        """Translate an HTTP failure into the shared taxonomy."""
        status = response.status_code
        detail = self._error_detail(response)

        match status:
            case 401 | 403:
                kind = ErrorKind.AUTHENTICATION
            case 404:
                kind = ErrorKind.INVALID_REQUEST
            case 408:
                kind = ErrorKind.TIMEOUT
            case 429:
                kind = ErrorKind.RATE_LIMITED
            case 400 | 422:
                # Context-length failures arrive as ordinary 400s but mean something
                # actionable: a different model, not a retry.
                lowered = detail.lower()
                kind = (
                    ErrorKind.CONTEXT_LENGTH_EXCEEDED
                    if "context" in lowered and "length" in lowered
                    else ErrorKind.INVALID_REQUEST
                )
            case _ if status >= 500:
                kind = ErrorKind.PROVIDER_UNAVAILABLE
            case _:
                kind = ErrorKind.UNKNOWN

        logger.warning(
            "provider_request_failed",
            provider=self.name,
            status_code=status,
            error_kind=kind.value,
        )
        return ProviderError(kind, f"{self.name}: {detail}", provider=self.name, status_code=status)

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text[:200] or f"HTTP {response.status_code}"
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return str(error["message"])[:500]
            if isinstance(error, str):
                return error[:500]
        return f"HTTP {response.status_code}"

    def _parse_response(
        self, body: dict[str, object], request: CompletionRequest, latency_ms: float
    ) -> CompletionResponse:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                f"{self.name}: response contained no choices",
                provider=self.name,
            )

        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                f"{self.name}: response message had no text content",
                provider=self.name,
            )

        usage_body = body.get("usage")
        usage = TokenUsage()
        if isinstance(usage_body, dict):
            usage = TokenUsage(
                input_tokens=int(usage_body.get("prompt_tokens", 0) or 0),
                output_tokens=int(usage_body.get("completion_tokens", 0) or 0),
            )
        if usage.total_tokens == 0:
            # Some compatible gateways omit usage; estimate so cost tracking never
            # silently reports zero spend.
            usage = TokenUsage(
                input_tokens=estimate_tokens(request.system_prompt + request.user_prompt),
                output_tokens=estimate_tokens(content),
            )

        finish_reason = first.get("finish_reason") if isinstance(first, dict) else None
        return CompletionResponse(
            text=content,
            usage=usage,
            model=request.model.id,
            provider=self.name,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _parse_stream_line(line: str) -> str | None:
        if not line.startswith("data:"):
            return None
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            return None
        try:
            event = json.loads(data)
        except ValueError:
            return None
        choices = event.get("choices") if isinstance(event, dict) else None
        if not isinstance(choices, list) or not choices:
            return None
        delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
        content = delta.get("content") if isinstance(delta, dict) else None
        return content if isinstance(content, str) and content else None


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    base_url = "https://api.openai.com/v1"
    models = (
        ModelSpec(
            id="openai:gpt-4o",
            provider="openai",
            model_name="gpt-4o",
            traits=frozenset(
                {
                    ModelTrait.REASONING,
                    ModelTrait.CODING,
                    ModelTrait.LONG_CONTEXT,
                    ModelTrait.STRUCTURED_OUTPUT,
                }
            ),
            context_tokens=128_000,
            max_output_tokens=16_384,
            input_cost_per_million=2.50,
            output_cost_per_million=10.0,
            typical_latency_ms=4_000,
        ),
        ModelSpec(
            id="openai:gpt-4o-mini",
            provider="openai",
            model_name="gpt-4o-mini",
            traits=frozenset(
                {
                    ModelTrait.FAST,
                    ModelTrait.CHEAP,
                    ModelTrait.CODING,
                    ModelTrait.STRUCTURED_OUTPUT,
                }
            ),
            context_tokens=128_000,
            max_output_tokens=16_384,
            input_cost_per_million=0.15,
            output_cost_per_million=0.60,
            typical_latency_ms=1_500,
        ),
    )


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    base_url = "https://api.deepseek.com/v1"
    models = (
        ModelSpec(
            id="deepseek:deepseek-chat",
            provider="deepseek",
            model_name="deepseek-chat",
            traits=frozenset(
                {
                    ModelTrait.CHEAP,
                    ModelTrait.CODING,
                    ModelTrait.LONG_CONTEXT,
                    ModelTrait.STRUCTURED_OUTPUT,
                    ModelTrait.FAST,
                }
            ),
            context_tokens=128_000,
            max_output_tokens=8_192,
            input_cost_per_million=0.27,
            output_cost_per_million=1.10,
            typical_latency_ms=3_000,
        ),
        ModelSpec(
            id="deepseek:deepseek-reasoner",
            provider="deepseek",
            model_name="deepseek-reasoner",
            traits=frozenset({ModelTrait.REASONING, ModelTrait.CODING}),
            context_tokens=128_000,
            max_output_tokens=8_192,
            input_cost_per_million=0.55,
            output_cost_per_million=2.19,
            typical_latency_ms=8_000,
        ),
    )


class XAIProvider(OpenAICompatibleProvider):
    name = "xai"
    base_url = "https://api.x.ai/v1"
    models = (
        ModelSpec(
            id="xai:grok-2",
            provider="xai",
            model_name="grok-2",
            traits=frozenset(
                {
                    ModelTrait.REASONING,
                    ModelTrait.CODING,
                    ModelTrait.LONG_CONTEXT,
                    ModelTrait.STRUCTURED_OUTPUT,
                }
            ),
            context_tokens=131_072,
            max_output_tokens=16_384,
            input_cost_per_million=2.0,
            output_cost_per_million=10.0,
            typical_latency_ms=4_000,
        ),
    )


class MistralProvider(OpenAICompatibleProvider):
    name = "mistral"
    base_url = "https://api.mistral.ai/v1"
    models = (
        ModelSpec(
            id="mistral:mistral-large-latest",
            provider="mistral",
            model_name="mistral-large-latest",
            traits=frozenset(
                {ModelTrait.REASONING, ModelTrait.CODING, ModelTrait.STRUCTURED_OUTPUT}
            ),
            context_tokens=128_000,
            max_output_tokens=16_384,
            input_cost_per_million=2.0,
            output_cost_per_million=6.0,
            typical_latency_ms=3_500,
        ),
        ModelSpec(
            id="mistral:mistral-small-latest",
            provider="mistral",
            model_name="mistral-small-latest",
            traits=frozenset({ModelTrait.FAST, ModelTrait.CHEAP, ModelTrait.STRUCTURED_OUTPUT}),
            context_tokens=128_000,
            max_output_tokens=8_192,
            input_cost_per_million=0.10,
            output_cost_per_million=0.30,
            typical_latency_ms=1_200,
        ),
    )


class GeminiProvider(OpenAICompatibleProvider):
    """Google Gemini via the OpenAI-compatible Generative Language endpoint."""

    name = "google"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    models = (
        ModelSpec(
            id="google:gemini-1.5-pro",
            provider="google",
            model_name="gemini-1.5-pro",
            traits=frozenset(
                {
                    ModelTrait.REASONING,
                    ModelTrait.LONG_CONTEXT,
                    ModelTrait.STRUCTURED_OUTPUT,
                    ModelTrait.CODING,
                }
            ),
            context_tokens=2_000_000,
            max_output_tokens=8_192,
            input_cost_per_million=1.25,
            output_cost_per_million=5.0,
            typical_latency_ms=3_500,
        ),
        ModelSpec(
            id="google:gemini-1.5-flash",
            provider="google",
            model_name="gemini-1.5-flash",
            traits=frozenset(
                {
                    ModelTrait.FAST,
                    ModelTrait.CHEAP,
                    ModelTrait.LONG_CONTEXT,
                    ModelTrait.STRUCTURED_OUTPUT,
                }
            ),
            context_tokens=1_000_000,
            max_output_tokens=8_192,
            input_cost_per_million=0.075,
            output_cost_per_million=0.30,
            typical_latency_ms=1_200,
        ),
    )


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    models = (
        ModelSpec(
            id="openrouter:openai/gpt-4o-mini",
            provider="openrouter",
            model_name="openai/gpt-4o-mini",
            traits=frozenset({ModelTrait.FAST, ModelTrait.CHEAP, ModelTrait.STRUCTURED_OUTPUT}),
            context_tokens=128_000,
            max_output_tokens=16_384,
            input_cost_per_million=0.15,
            output_cost_per_million=0.60,
            typical_latency_ms=2_000,
        ),
    )
