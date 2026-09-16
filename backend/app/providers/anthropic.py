"""Adapter for Anthropic's Messages API.

The request and response shapes differ from OpenAI-compatible providers (system is a
top-level field, content is a list of blocks, errors use ``error.type``). Mapping those
onto ``CompletionResponse`` / ``ProviderError`` here keeps the executor vendor-blind.
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

_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    base_url = "https://api.anthropic.com/v1"
    models = (
        ModelSpec(
            id="anthropic:claude-3-5-sonnet-latest",
            provider="anthropic",
            model_name="claude-3-5-sonnet-latest",
            traits=frozenset(
                {
                    ModelTrait.REASONING,
                    ModelTrait.CODING,
                    ModelTrait.LONG_CONTEXT,
                    ModelTrait.STRUCTURED_OUTPUT,
                }
            ),
            context_tokens=200_000,
            max_output_tokens=8_192,
            input_cost_per_million=3.0,
            output_cost_per_million=15.0,
            typical_latency_ms=4_000,
        ),
        ModelSpec(
            id="anthropic:claude-3-5-haiku-latest",
            provider="anthropic",
            model_name="claude-3-5-haiku-latest",
            traits=frozenset(
                {ModelTrait.FAST, ModelTrait.CHEAP, ModelTrait.CODING, ModelTrait.STRUCTURED_OUTPUT}
            ),
            context_tokens=200_000,
            max_output_tokens=8_192,
            input_cost_per_million=0.80,
            output_cost_per_million=4.0,
            typical_latency_ms=1_500,
        ),
    )

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or self.base_url).rstrip("/")
        self._client = client

    def validate_configuration(self) -> None:
        if not self._api_key:
            raise ProviderConfigurationError(
                f"{self.name}: no API key configured", provider=self.name
            )

    def get_model_capabilities(self) -> tuple[ModelSpec, ...]:
        return self.models

    def estimate_cost(self, request: CompletionRequest) -> float:
        prompt_tokens = estimate_tokens(request.system_prompt + request.user_prompt)
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
                f"{self._base_url}/messages",
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
                f"{self._base_url}/messages",
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

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key or "",
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    async def list_remote_model_ids(self, *, timeout_seconds: float = 30.0) -> list[str]:
        """Discover model ids from Anthropic's ``GET /v1/models`` endpoint."""
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
        user_prompt = request.user_prompt
        if request.response_schema is not None:
            user_prompt = (
                f"{user_prompt}\n\nRespond with a JSON object matching this schema:\n"
                f"{json.dumps(request.response_schema)}"
            )
        payload: dict[str, object] = {
            "model": request.model.model_name,
            "max_tokens": min(request.max_output_tokens, request.model.max_output_tokens),
            "temperature": request.temperature,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if stream:
            payload["stream"] = True
        return payload

    def _map_error(self, response: httpx.Response) -> ProviderError:
        status = response.status_code
        detail, error_type = self._error_detail(response)
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
                lowered = f"{detail} {error_type}".lower()
                if "content" in lowered and "filter" in lowered:
                    kind = ErrorKind.CONTENT_FILTERED
                elif "context" in lowered and "length" in lowered:
                    kind = ErrorKind.CONTEXT_LENGTH_EXCEEDED
                else:
                    kind = ErrorKind.INVALID_REQUEST
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
    def _error_detail(response: httpx.Response) -> tuple[str, str]:
        try:
            body = response.json()
        except ValueError:
            return (response.text[:200] or f"HTTP {response.status_code}", "")
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                error_type = error.get("type")
                text = message if isinstance(message, str) else f"HTTP {response.status_code}"
                return (text[:500], error_type if isinstance(error_type, str) else "")
            if isinstance(error, str):
                return (error[:500], "")
        return (f"HTTP {response.status_code}", "")

    def _parse_response(
        self, body: dict[str, object], request: CompletionRequest, latency_ms: float
    ) -> CompletionResponse:
        stop_reason = body.get("stop_reason")
        if stop_reason == "refusal":
            raise ProviderError(
                ErrorKind.CONTENT_FILTERED,
                f"{self.name}: response was refused",
                provider=self.name,
            )

        blocks = body.get("content")
        if not isinstance(blocks, list) or not blocks:
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                f"{self.name}: response contained no content blocks",
                provider=self.name,
            )

        texts: list[str] = []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
        content = "".join(texts)
        if not content:
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                f"{self.name}: response had no text content",
                provider=self.name,
            )

        usage_body = body.get("usage")
        usage = TokenUsage()
        if isinstance(usage_body, dict):
            usage = TokenUsage(
                input_tokens=int(usage_body.get("input_tokens", 0) or 0),
                output_tokens=int(usage_body.get("output_tokens", 0) or 0),
            )
        if usage.total_tokens == 0:
            usage = TokenUsage(
                input_tokens=estimate_tokens(request.system_prompt + request.user_prompt),
                output_tokens=estimate_tokens(content),
            )

        return CompletionResponse(
            text=content,
            usage=usage,
            model=request.model.id,
            provider=self.name,
            finish_reason=stop_reason if isinstance(stop_reason, str) else None,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _parse_stream_line(line: str) -> str | None:
        if not line.startswith("data:"):
            return None
        data = line.removeprefix("data:").strip()
        if not data:
            return None
        try:
            event = json.loads(data)
        except ValueError:
            return None
        if not isinstance(event, dict) or event.get("type") != "content_block_delta":
            return None
        delta = event.get("delta")
        text = delta.get("text") if isinstance(delta, dict) else None
        return text if isinstance(text, str) and text else None
