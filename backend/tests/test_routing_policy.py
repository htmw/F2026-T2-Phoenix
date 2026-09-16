"""Routing policy: provider priority and blocked models."""

from __future__ import annotations

from httpx import AsyncClient

from app.domain.enums import ModelTrait
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.agent import ModelPreference
from app.services.routing_policy import RoutingPolicy


def test_blocked_models_are_skipped_unless_pinned() -> None:
    registry = ProviderRegistry(
        [FakeProvider()],
        policy=RoutingPolicy(blocked_models=frozenset({"fake:reasoner"})),
    )
    ranked = registry.rank_models(ModelPreference(min_context_tokens=1_000))
    assert all(item.model.id != "fake:reasoner" for item in ranked)
    assert ranked[0].model.id == "fake:cheap"

    pinned = registry.rank_models(
        ModelPreference(preferred_model="fake:reasoner", min_context_tokens=1_000)
    )
    assert pinned[0].model.id == "fake:reasoner"


def test_provider_priority_reorders_auto_routing() -> None:
    from app.providers.base import ModelSpec
    from app.providers.fake import FAKE_MODELS

    alpha_models = tuple(
        ModelSpec(
            id=f"alpha:{model.model_name}",
            provider="alpha",
            model_name=model.model_name,
            traits=model.traits,
            context_tokens=model.context_tokens,
            max_output_tokens=model.max_output_tokens,
            input_cost_per_million=model.input_cost_per_million,
            output_cost_per_million=model.output_cost_per_million,
            typical_latency_ms=model.typical_latency_ms,
        )
        for model in FAKE_MODELS
    )
    beta_models = tuple(
        ModelSpec(
            id=f"beta:{model.model_name}",
            provider="beta",
            model_name=model.model_name,
            traits=model.traits,
            context_tokens=model.context_tokens,
            max_output_tokens=model.max_output_tokens,
            input_cost_per_million=model.input_cost_per_million,
            # Cost alone would prefer alpha; priority should still pick beta.
            output_cost_per_million=model.output_cost_per_million + 100,
            typical_latency_ms=model.typical_latency_ms,
        )
        for model in FAKE_MODELS
    )
    alpha = FakeProvider(models=alpha_models)
    alpha.name = "alpha"
    beta = FakeProvider(models=beta_models)
    beta.name = "beta"

    registry = ProviderRegistry(
        [alpha, beta],
        policy=RoutingPolicy(provider_priority=("beta", "alpha")),
    )
    winner = registry.select_model(
        ModelPreference(required_traits=(ModelTrait.CODING,), min_context_tokens=1_000)
    )
    assert winner[0].name == "beta"
    assert winner[1].id.startswith("beta:")


async def test_routing_policy_api_round_trip(db_client: AsyncClient) -> None:
    empty = await db_client.get("/api/v1/providers/routing-policy")
    assert empty.status_code == 200
    assert empty.json()["provider_priority"] == []
    assert empty.json()["blocked_models"] == []

    updated = await db_client.put(
        "/api/v1/providers/routing-policy",
        json={
            "provider_priority": ["openai", "anthropic"],
            "blocked_models": ["openai:gpt-4o"],
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["provider_priority"] == ["openai", "anthropic"]
    assert body["blocked_models"] == ["openai:gpt-4o"]

    again = await db_client.get("/api/v1/providers/routing-policy")
    assert again.json() == body


async def test_routing_policy_rejects_bad_model_id(db_client: AsyncClient) -> None:
    response = await db_client.put(
        "/api/v1/providers/routing-policy",
        json={"provider_priority": [], "blocked_models": ["not-a-model"]},
    )
    assert response.status_code == 422
