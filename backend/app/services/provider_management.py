"""Provider catalogue metadata and connection management operations."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import ErrorKind, ProviderConnectionStatus
from app.providers.anthropic import AnthropicProvider
from app.providers.base import LLMProvider, ProviderError
from app.providers.openai_compatible import (
    CohereProvider,
    DeepSeekProvider,
    GeminiProvider,
    GroqProvider,
    MistralProvider,
    MoonshotProvider,
    OpenAIProvider,
    OpenRouterProvider,
    PerplexityProvider,
    QwenProvider,
    TogetherProvider,
    XAIProvider,
)
from app.providers.registry import ProviderRegistry, build_provider_registry
from app.services import provider_connections as connections

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderCatalogEntry:
    id: str
    label: str
    auth_method: str = "api_key"
    access_label: str = "API"


PROVIDER_CATALOG: tuple[ProviderCatalogEntry, ...] = (
    ProviderCatalogEntry("openai", "OpenAI (ChatGPT)"),
    ProviderCatalogEntry("anthropic", "Claude (Anthropic)"),
    ProviderCatalogEntry("google", "Google Gemini"),
    ProviderCatalogEntry("moonshot", "Kimi (Moonshot)"),
    ProviderCatalogEntry("groq", "Groq"),
    ProviderCatalogEntry("deepseek", "DeepSeek"),
    ProviderCatalogEntry("xai", "xAI (Grok)"),
    ProviderCatalogEntry("mistral", "Mistral"),
    ProviderCatalogEntry("cohere", "Cohere"),
    ProviderCatalogEntry("perplexity", "Perplexity"),
    ProviderCatalogEntry("together", "Together AI"),
    ProviderCatalogEntry("qwen", "Qwen (Alibaba)"),
    ProviderCatalogEntry("openrouter", "OpenRouter"),
)

_PROVIDER_LABELS = {entry.id: entry.label for entry in PROVIDER_CATALOG}
_PROVIDER_LABELS["fake"] = "Demo Mode (development)"


def provider_label(provider_id: str) -> str:
    return _PROVIDER_LABELS.get(provider_id, provider_id.title())


def env_key_for(settings: Settings, provider_id: str) -> str | None:
    mapping = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "google": settings.google_api_key,
        "deepseek": settings.deepseek_api_key,
        "xai": settings.xai_api_key,
        "mistral": settings.mistral_api_key,
        "openrouter": settings.openrouter_api_key,
        "groq": settings.groq_api_key,
        "moonshot": settings.moonshot_api_key,
        "cohere": settings.cohere_api_key,
        "perplexity": settings.perplexity_api_key,
        "together": settings.together_api_key,
        "qwen": settings.qwen_api_key,
    }
    secret = mapping.get(provider_id)
    if secret is None:
        return None
    return secret.get_secret_value()


def make_provider(provider_id: str, api_key: str) -> LLMProvider:
    factories: dict[str, type[LLMProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GeminiProvider,
        "deepseek": DeepSeekProvider,
        "xai": XAIProvider,
        "mistral": MistralProvider,
        "openrouter": OpenRouterProvider,
        "groq": GroqProvider,
        "moonshot": MoonshotProvider,
        "cohere": CohereProvider,
        "perplexity": PerplexityProvider,
        "together": TogetherProvider,
        "qwen": QwenProvider,
    }
    factory = factories.get(provider_id)
    if factory is None:
        raise KeyError(provider_id)
    return factory(api_key)  # type: ignore[call-arg]


async def discover_models(provider: LLMProvider) -> list[str]:
    list_fn = getattr(provider, "list_remote_model_ids", None)
    if list_fn is None:
        return [model.model_name for model in provider.get_model_capabilities()]
    return list(await list_fn())


async def test_provider_key(provider_id: str, api_key: str) -> tuple[ProviderConnectionStatus, list[str], str | None]:
    """Validate a key by listing models (or falling back to catalogue presence)."""
    try:
        provider = make_provider(provider_id, api_key)
        provider.validate_configuration()
        remote = await discover_models(provider)
        if not remote and not provider.get_model_capabilities():
            return ProviderConnectionStatus.NO_MODELS, [], "No usable models were discovered."
        return ProviderConnectionStatus.CONNECTED, remote, None
    except ProviderError as exc:
        if exc.kind is ErrorKind.AUTHENTICATION:
            return ProviderConnectionStatus.AUTH_FAILED, [], exc.message
        return ProviderConnectionStatus.UNAVAILABLE, [], exc.message
    except Exception as exc:  # noqa: BLE001
        return ProviderConnectionStatus.UNAVAILABLE, [], str(exc)


async def rebuild_app_registry(request: Request, session: AsyncSession, settings: Settings) -> ProviderRegistry:
    from app.services import routing_policy as routing_policy_service

    overrides = await connections.load_connection_secrets(session, settings)
    policy = await routing_policy_service.get_policy(session)
    registry = build_provider_registry(
        settings, credential_overrides=overrides, policy=policy
    )
    request.app.state.provider_registry = registry
    runner = getattr(request.app.state, "workflow_runner", None)
    if runner is not None:
        runner.replace_providers(registry)
    logger.info("provider_registry_rebuilt", providers=registry.names)
    return registry


def redact_error(message: str) -> str:
    """Strip anything that looks like a bearer token from error text."""
    lowered = message.lower()
    if "sk-" in lowered or "bearer " in lowered or "api_key" in lowered:
        return "Provider rejected the credential or request."
    return message[:240]
