"""Provider registry and model selection.

Providers are built from configuration: a provider with no credential is simply absent
rather than a startup failure, so a developer with one key can still run the platform.

Selection is trait-first, then cost, then latency. The ranked list is what fallback
walks when a chosen provider is down: the next survivor is already the next-best model,
not a random retry of the same one.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import ModelTrait
from app.providers.anthropic import AnthropicProvider
from app.providers.base import LLMProvider, ModelSpec
from app.providers.fake import FakeProvider
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
from app.schemas.agent import ModelPreference
from app.services.routing_policy import RoutingPolicy

logger = get_logger(__name__)


class NoSuitableModelError(RuntimeError):
    """Raised when no configured provider offers a model meeting the requirements."""


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Why this provider and model were chosen, and what else was eligible.

    Persisted in logs (never secrets) so "why did this agent cost that much" is
    answerable after the fact. ``alternatives`` is the rest of the ranked list, which is
    also the fallback order.
    """

    provider: LLMProvider
    model: ModelSpec
    reason: str
    alternatives: tuple[tuple[str, str], ...] = ()


class ProviderRegistry:
    """Holds the configured providers and picks models for agents."""

    def __init__(
        self,
        providers: list[LLMProvider],
        *,
        policy: RoutingPolicy | None = None,
    ) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self._policy = policy or RoutingPolicy()

    @property
    def policy(self) -> RoutingPolicy:
        return self._policy

    @property
    def names(self) -> list[str]:
        return sorted(self._providers)

    @property
    def only_fake(self) -> bool:
        """True when no live vendor is configured — hive consult stays off in that case."""
        return bool(self._providers) and all(
            provider.name == "fake" for provider in self._providers.values()
        )

    def get(self, name: str) -> LLMProvider:
        try:
            return self._providers[name]
        except KeyError:
            raise NoSuitableModelError(f"provider '{name}' is not configured") from None

    def available_models(self) -> list[ModelSpec]:
        return [
            model
            for provider in self._providers.values()
            for model in provider.get_model_capabilities()
        ]

    def rank_models(self, preference: ModelPreference) -> list[RoutingDecision]:
        """Every eligible model, best first.

        Hard filters: required traits, context size, and blocked models (blocked ids are
        skipped unless they are an explicit Fixed ``preferred_model``). Soft ranking:
        operator provider priority, preferred provider, preferred traits, cost, latency.
        """
        preferred = frozenset(preference.preferred_traits)
        pinned_id = preference.preferred_model
        ranked: list[tuple[tuple[int, int, int, float, int, str], LLMProvider, ModelSpec]] = []
        for provider in self._providers.values():
            for model in provider.get_model_capabilities():
                if self._policy.is_blocked(model.id) and model.id != pinned_id:
                    continue
                if not model.supports(frozenset(preference.required_traits)):
                    continue
                if model.context_tokens < preference.min_context_tokens:
                    continue
                vendor_penalty = (
                    0
                    if not preference.preferred_provider
                    or provider.name == preference.preferred_provider
                    else 1
                )
                missing_preferred = len(preferred - model.traits)
                score = (
                    self._policy.provider_rank(provider.name),
                    vendor_penalty,
                    missing_preferred,
                    model.output_cost_per_million,
                    model.typical_latency_ms,
                    model.id,
                )
                ranked.append((score, provider, model))

        ranked.sort(key=lambda item: item[0])

        if preference.preferred_model:
            pinned = [item for item in ranked if item[2].id == preference.preferred_model]
            rest = [item for item in ranked if item[2].id != preference.preferred_model]
            if pinned:
                ranked = [*pinned, *rest]
            else:
                # An explicit operator pin wins even when the model fails the agent's
                # usual trait filters — that is the point of choosing a model by hand.
                for provider in self._providers.values():
                    for model in provider.get_model_capabilities():
                        if model.id == preference.preferred_model:
                            ranked.insert(0, ((-1, -1, 0, 0.0, 0, model.id), provider, model))
                            break
                    else:
                        continue
                    break

        if not ranked:
            raise NoSuitableModelError(
                "no configured model provides traits "
                f"{sorted(t.value for t in preference.required_traits)} with at least "
                f"{preference.min_context_tokens} context tokens"
            )

        decisions: list[RoutingDecision] = []
        for index, (_score, provider, model) in enumerate(ranked):
            alternatives = tuple((p.name, m.id) for _, p, m in ranked[index + 1 :])
            decisions.append(
                RoutingDecision(
                    provider=provider,
                    model=model,
                    reason=_reason(
                        preference,
                        provider,
                        model,
                        len(ranked),
                        index == 0,
                        self._policy,
                    ),
                    alternatives=alternatives,
                )
            )
        return decisions

    def select_model(self, preference: ModelPreference) -> tuple[LLMProvider, ModelSpec]:
        """Choose a provider and model satisfying an agent's stated preference.

        Convenience for callers that only need the winner. Fallback walks ``rank_models``.
        """
        winner = self.rank_models(preference)[0]
        logger.info(
            "model_routed",
            provider=winner.provider.name,
            model=winner.model.id,
            reason=winner.reason,
            alternatives=[f"{name}:{model}" for name, model in winner.alternatives[:5]],
        )
        return winner.provider, winner.model

    def route(self, preference: ModelPreference) -> RoutingDecision:
        decision = self.rank_models(preference)[0]
        logger.info(
            "model_routed",
            provider=decision.provider.name,
            model=decision.model.id,
            reason=decision.reason,
            alternatives=[f"{name}:{model}" for name, model in decision.alternatives[:5]],
        )
        return decision


def _reason(
    preference: ModelPreference,
    provider: LLMProvider,
    model: ModelSpec,
    candidate_count: int,
    primary: bool,
    policy: RoutingPolicy,
) -> str:
    if preference.preferred_model and model.id == preference.preferred_model:
        return f"pinned to {model.id}"
    if policy.provider_priority and provider.name in policy.provider_priority:
        rank = policy.provider_rank(provider.name) + 1
        if preference.preferred_provider and provider.name == preference.preferred_provider:
            return (
                f"preferred provider {provider.name} (office priority #{rank}); "
                f"{model.id} is the cheapest match on that vendor"
            )
        if primary and policy.provider_rank(provider.name) == 0:
            return (
                f"office priority prefers {provider.name}; {model.id} best match among "
                f"{candidate_count} candidates"
            )
    if preference.preferred_provider and provider.name == preference.preferred_provider:
        return (
            f"preferred provider {provider.name}; {model.id} is the cheapest match on that vendor"
        )
    preferred = frozenset(preference.preferred_traits)
    if preferred and preferred <= model.traits:
        traits = ", ".join(sorted(trait.value for trait in preferred))
        return (
            f"{model.id} matches preferred traits [{traits}] at "
            f"${model.output_cost_per_million}/M output among {candidate_count} candidates"
        )
    prefix = "selected" if primary else "fallback"
    return (
        f"{prefix} {model.id}: lowest cost among {candidate_count} models meeting "
        f"required traits and {preference.min_context_tokens} context tokens"
    )


def build_provider_registry(
    settings: Settings,
    *,
    include_fake: bool | None = None,
    credential_overrides: dict[str, str] | None = None,
    policy: RoutingPolicy | None = None,
) -> ProviderRegistry:
    """Construct the registry from configuration and optional Settings-stored keys.

    Stored connection secrets override environment values for the same provider id.
    The fake provider is included only when no real provider is configured and the
    environment is not production (unless ``include_fake`` forces it).
    """
    overrides = credential_overrides or {}

    def resolve(name: str, env_key: SecretStr | None) -> str | None:
        if name in overrides and overrides[name].strip():
            return overrides[name].strip()
        if env_key is not None:
            return env_key.get_secret_value()
        return None

    candidates: list[LLMProvider] = [
        OpenAIProvider(resolve("openai", settings.openai_api_key)),
        AnthropicProvider(resolve("anthropic", settings.anthropic_api_key)),
        GeminiProvider(resolve("google", settings.google_api_key)),
        MoonshotProvider(resolve("moonshot", settings.moonshot_api_key)),
        DeepSeekProvider(resolve("deepseek", settings.deepseek_api_key)),
        XAIProvider(resolve("xai", settings.xai_api_key)),
        MistralProvider(resolve("mistral", settings.mistral_api_key)),
        CohereProvider(resolve("cohere", settings.cohere_api_key)),
        PerplexityProvider(resolve("perplexity", settings.perplexity_api_key)),
        TogetherProvider(resolve("together", settings.together_api_key)),
        QwenProvider(resolve("qwen", settings.qwen_api_key)),
        OpenRouterProvider(resolve("openrouter", settings.openrouter_api_key)),
        GroqProvider(resolve("groq", settings.groq_api_key)),
    ]

    configured = [provider for provider in candidates if provider.is_configured()]

    if include_fake is None:
        use_fake = not configured and not settings.is_production
    else:
        use_fake = include_fake
    if use_fake:
        configured.append(FakeProvider())
        if not settings.is_production:
            logger.warning(
                "using_demo_provider",
                reason="no provider credentials configured",
                hint=(
                    "Demo Mode only — connect a provider in Settings or set an API key "
                    "in .env for real calls"
                ),
            )

    logger.info("provider_registry_built", providers=[p.name for p in configured])
    return ProviderRegistry(configured, policy=policy)


def cheapest_model_with(registry: ProviderRegistry, trait: ModelTrait) -> ModelSpec | None:
    """Utility for diagnostics and the model catalogue endpoint."""
    models = [model for model in registry.available_models() if trait in model.traits]
    return min(models, key=lambda m: m.output_cost_per_million) if models else None
