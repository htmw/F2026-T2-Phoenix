"""Provider tests.

No test here makes a network call. The HTTP adapter is exercised through an injected
``httpx`` transport, so request shaping and error mapping are verified without spending
money or depending on a vendor being up.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.domain.enums import ErrorKind, ModelTrait
from app.providers.anthropic import AnthropicProvider
from app.providers.base import (
    CompletionRequest,
    LLMProvider,
    ProviderConfigurationError,
    ProviderError,
    estimate_tokens,
)
from app.providers.fake import FAKE_MODELS, FakeProvider
from app.providers.openai_compatible import (
    DeepSeekProvider,
    GeminiProvider,
    MistralProvider,
    OpenAIProvider,
    OpenRouterProvider,
)
from app.providers.registry import (
    NoSuitableModelError,
    ProviderRegistry,
    build_provider_registry,
)
from app.schemas.agent import ModelPreference
from app.schemas.execution import TokenUsage

CHEAP_MODEL = FAKE_MODELS[1]
REASONER = FAKE_MODELS[0]


def request_for(model: object = REASONER, **overrides: object) -> CompletionRequest:
    defaults: dict[str, object] = {
        "model": model,
        "system_prompt": "You are a test agent.",
        "user_prompt": "Do the thing.",
        "max_output_tokens": 1_000,
    }
    defaults.update(overrides)
    return CompletionRequest(**defaults)  # type: ignore[arg-type]


def stub_transport(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Conformance: every adapter must behave the same way on these points
# ---------------------------------------------------------------------------


def all_adapters() -> list[LLMProvider]:
    return [
        FakeProvider(),
        OpenAIProvider("sk-test-key"),
        DeepSeekProvider("sk-test-key"),
        AnthropicProvider("sk-test-key"),
        GeminiProvider("sk-test-key"),
        MistralProvider("sk-test-key"),
        OpenRouterProvider("sk-test-key"),
    ]


@pytest.mark.parametrize("provider", all_adapters(), ids=lambda p: p.name)
def test_adapter_declares_a_name(provider: LLMProvider) -> None:
    assert provider.name
    assert provider.name == provider.name.lower()


@pytest.mark.parametrize("provider", all_adapters(), ids=lambda p: p.name)
def test_adapter_declares_models_with_pricing(provider: LLMProvider) -> None:
    models = provider.get_model_capabilities()

    assert models
    for model in models:
        assert model.provider == provider.name
        assert model.context_tokens > 0
        assert model.output_cost_per_million >= 0


@pytest.mark.parametrize("provider", all_adapters(), ids=lambda p: p.name)
def test_configured_adapter_validates(provider: LLMProvider) -> None:
    provider.validate_configuration()
    assert provider.is_configured() is True


@pytest.mark.parametrize("provider", all_adapters(), ids=lambda p: p.name)
def test_cost_estimate_is_positive_and_conservative(provider: LLMProvider) -> None:
    model = provider.get_model_capabilities()[0]
    estimate = provider.estimate_cost(request_for(model, max_output_tokens=1_000))

    # The estimate guards a spend limit, so it must assume the full output allowance
    # rather than a hopeful minimum.
    actual_for_one_token = model.cost_for(TokenUsage(input_tokens=10, output_tokens=1))
    assert estimate > actual_for_one_token


def test_unconfigured_adapter_reports_itself_unusable() -> None:
    provider = OpenAIProvider(api_key=None)

    assert provider.is_configured() is False
    with pytest.raises(ProviderConfigurationError):
        provider.validate_configuration()


async def test_unconfigured_adapter_refuses_to_call() -> None:
    provider = OpenAIProvider(api_key=None)

    with pytest.raises(ProviderConfigurationError):
        await provider.generate(request_for(provider.models[0]))


# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------


async def test_fake_provider_returns_queued_response() -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": ["one"]})

    response = await provider.generate(request_for())

    assert json.loads(response.text) == {"findings": ["one"]}
    assert response.usage.total_tokens > 0


async def test_fake_provider_raises_queued_failure() -> None:
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.RATE_LIMITED, "slow down")

    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for())

    assert caught.value.kind is ErrorKind.RATE_LIMITED
    assert caught.value.is_retryable is True


async def test_fake_provider_generates_schema_shaped_stub() -> None:
    provider = FakeProvider()
    schema = {
        "type": "object",
        "required": ["passed", "tests"],
        "properties": {
            "passed": {"type": "boolean"},
            "tests": {"type": "array"},
        },
    }

    response = await provider.generate(request_for(response_schema=schema))

    assert json.loads(response.text) == {"passed": True, "tests": []}


async def test_fake_provider_records_requests() -> None:
    provider = FakeProvider()
    await provider.generate(request_for(user_prompt="specific objective"))

    assert provider.requests[0].user_prompt == "specific objective"


async def test_fake_provider_streams_the_same_text() -> None:
    provider = FakeProvider(default_response="alpha beta gamma")

    chunks = [chunk async for chunk in provider.stream(request_for())]

    assert "".join(chunks).strip() == "alpha beta gamma"


# ---------------------------------------------------------------------------
# OpenAI-compatible adapter: request shaping
# ---------------------------------------------------------------------------


async def test_adapter_sends_system_and_user_messages() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))
    await provider.generate(request_for(provider.models[0]))

    messages = captured["messages"]
    assert isinstance(messages, list)
    assert [message["role"] for message in messages] == ["system", "user"]


async def test_adapter_sends_the_credential_as_a_bearer_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}], "usage": {}},
        )

    provider = OpenAIProvider("sk-secret", client=stub_transport(handler))
    await provider.generate(request_for(provider.models[0]))

    assert seen["auth"] == "Bearer sk-secret"


async def test_adapter_requests_json_mode_for_structured_models() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))
    await provider.generate(request_for(provider.models[0], response_schema={"type": "object"}))

    assert captured["response_format"] == {"type": "json_object"}


async def test_adapter_reports_token_usage_from_the_provider() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"a": 1}'}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 45},
            },
        )

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))
    response = await provider.generate(request_for(provider.models[0]))

    assert (response.usage.input_tokens, response.usage.output_tokens) == (120, 45)
    assert response.cost(provider.models[0]) > 0


async def test_adapter_estimates_usage_when_the_provider_omits_it() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))
    response = await provider.generate(request_for(provider.models[0]))

    # Reporting zero spend would make cost tracking quietly wrong for any gateway that
    # omits usage.
    assert response.usage.total_tokens > 0


# ---------------------------------------------------------------------------
# OpenAI-compatible adapter: error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status_code", "expected_kind", "retryable"),
    [
        (401, ErrorKind.AUTHENTICATION, False),
        (403, ErrorKind.AUTHENTICATION, False),
        (429, ErrorKind.RATE_LIMITED, True),
        (500, ErrorKind.PROVIDER_UNAVAILABLE, True),
        (503, ErrorKind.PROVIDER_UNAVAILABLE, True),
        (400, ErrorKind.INVALID_REQUEST, False),
    ],
)
async def test_http_status_maps_to_the_shared_taxonomy(
    status_code: int, expected_kind: ErrorKind, retryable: bool
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "upstream said no"}})

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))

    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for(provider.models[0]))

    assert caught.value.kind is expected_kind
    assert caught.value.is_retryable is retryable
    assert caught.value.status_code == status_code


async def test_context_length_error_is_distinguished_from_a_generic_400() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "This model's maximum context length is 8192 tokens"}},
        )

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))

    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for(provider.models[0]))

    # Actionable: route to a larger model rather than retry the same one.
    assert caught.value.kind is ErrorKind.CONTEXT_LENGTH_EXCEEDED


async def test_timeout_maps_to_timeout_kind() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))

    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for(provider.models[0]))

    assert caught.value.kind is ErrorKind.TIMEOUT


async def test_transport_failure_maps_to_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))

    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for(provider.models[0]))

    assert caught.value.kind is ErrorKind.PROVIDER_UNAVAILABLE


async def test_response_without_choices_is_invalid_output() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))

    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for(provider.models[0]))

    assert caught.value.kind is ErrorKind.INVALID_OUTPUT


async def test_provider_error_message_does_not_leak_the_api_key() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    provider = OpenAIProvider("sk-super-secret", client=stub_transport(handler))

    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for(provider.models[0]))

    assert "sk-super-secret" not in str(caught.value)


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------


def fake_only_registry() -> ProviderRegistry:
    return ProviderRegistry([FakeProvider()])


def test_required_traits_are_a_hard_filter() -> None:
    registry = fake_only_registry()

    _, model = registry.select_model(
        ModelPreference(required_traits=(ModelTrait.REASONING,), min_context_tokens=1_000)
    )

    assert ModelTrait.REASONING in model.traits


def test_selection_prefers_the_cheaper_model_when_traits_allow() -> None:
    registry = fake_only_registry()

    _, model = registry.select_model(
        ModelPreference(required_traits=(ModelTrait.STRUCTURED_OUTPUT,), min_context_tokens=1_000)
    )

    # Both fake models are structured-output capable; the cheap one must win so simple
    # work does not run on an expensive model.
    assert model.id == CHEAP_MODEL.id


def test_preferred_traits_break_ties_before_cost() -> None:
    registry = fake_only_registry()

    _, model = registry.select_model(
        ModelPreference(
            required_traits=(ModelTrait.STRUCTURED_OUTPUT,),
            preferred_traits=(ModelTrait.CODING,),
            min_context_tokens=1_000,
        )
    )

    assert model.id == REASONER.id


def test_context_requirement_excludes_small_models() -> None:
    registry = fake_only_registry()

    _, model = registry.select_model(ModelPreference(min_context_tokens=100_000))

    assert model.context_tokens >= 100_000


def test_explicit_model_pin_is_honoured() -> None:
    registry = fake_only_registry()

    _, model = registry.select_model(
        ModelPreference(preferred_model=REASONER.id, min_context_tokens=1_000)
    )

    assert model.id == REASONER.id


def test_unsatisfiable_requirements_raise_a_clear_error() -> None:
    registry = fake_only_registry()

    with pytest.raises(NoSuitableModelError, match="no configured model"):
        registry.select_model(ModelPreference(min_context_tokens=10_000_000))


def test_selection_is_deterministic() -> None:
    registry = fake_only_registry()
    preference = ModelPreference(min_context_tokens=1_000)

    picks = {registry.select_model(preference)[1].id for _ in range(5)}

    assert len(picks) == 1


# ---------------------------------------------------------------------------
# Registry construction from settings
# ---------------------------------------------------------------------------


def settings_with(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_registry_falls_back_to_the_fake_provider_without_credentials() -> None:
    registry = build_provider_registry(settings_with())

    # A fresh checkout must run end to end without keys, or nobody can try the product.
    assert registry.names == ["fake"]
    assert registry.only_fake is True


def test_production_never_registers_the_demo_provider() -> None:
    registry = build_provider_registry(settings_with(environment="production"))

    assert registry.names == []


def test_configured_provider_replaces_the_fake() -> None:
    registry = build_provider_registry(settings_with(openai_api_key="sk-test"))

    assert registry.names == ["openai"]


def test_multiple_credentials_produce_multiple_providers() -> None:
    registry = build_provider_registry(
        settings_with(openai_api_key="sk-a", deepseek_api_key="sk-b", xai_api_key="sk-c")
    )

    assert registry.names == ["deepseek", "openai", "xai"]


def test_a_missing_credential_disables_only_that_provider() -> None:
    registry = build_provider_registry(settings_with(deepseek_api_key="sk-b"))

    # A missing key must not crash startup; the provider is simply absent.
    assert registry.names == ["deepseek"]


def test_anthropic_is_configured_from_its_own_key() -> None:
    registry = build_provider_registry(settings_with(anthropic_api_key="sk-ant"))

    assert registry.names == ["anthropic"]


def test_google_is_configured_from_its_own_key() -> None:
    registry = build_provider_registry(settings_with(google_api_key="sk-google"))

    assert registry.names == ["google"]
    assert any(model.id.startswith("google:gemini") for model in registry.available_models())


def test_preferred_provider_is_chosen_when_it_can_serve() -> None:
    registry = build_provider_registry(
        settings_with(openai_api_key="sk-a", anthropic_api_key="sk-b"), include_fake=False
    )
    decision = registry.route(
        ModelPreference(
            required_traits=(ModelTrait.CODING,),
            preferred_provider="anthropic",
            min_context_tokens=1_000,
        )
    )

    assert decision.provider.name == "anthropic"
    assert "preferred provider" in decision.reason
    assert decision.alternatives


def test_routing_logs_a_reason_and_keeps_fallbacks() -> None:
    registry = fake_only_registry()
    ranked = registry.rank_models(ModelPreference(min_context_tokens=1_000))

    assert ranked[0].reason
    assert ranked[0].alternatives
    assert ranked[0].alternatives[0][0] == "fake"


def test_estimate_tokens_is_conservative_but_bounded() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------


async def test_anthropic_sends_system_as_a_top_level_field() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers["x-api-key"]
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 9, "output_tokens": 4},
            },
        )

    provider = AnthropicProvider("sk-ant-secret", client=stub_transport(handler))
    response = await provider.generate(request_for(provider.models[0]))

    url = captured["url"]
    assert isinstance(url, str) and url.endswith("/messages")
    assert captured["key"] == "sk-ant-secret"
    assert captured["system"] == "You are a test agent."
    assert response.usage.input_tokens == 9
    assert "sk-ant-secret" not in str(response)


async def test_anthropic_maps_overloaded_to_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            529,
            json={"error": {"type": "overloaded_error", "message": "overloaded"}},
        )

    provider = AnthropicProvider("sk-test", client=stub_transport(handler))
    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for(provider.models[0]))

    assert caught.value.kind is ErrorKind.PROVIDER_UNAVAILABLE


async def test_anthropic_refusal_is_content_filtered() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "no"}],
                "stop_reason": "refusal",
            },
        )

    provider = AnthropicProvider("sk-test", client=stub_transport(handler))
    with pytest.raises(ProviderError) as caught:
        await provider.generate(request_for(provider.models[0]))

    assert caught.value.kind is ErrorKind.CONTENT_FILTERED
