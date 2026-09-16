"""Operator-chosen agent roster and per-agent model pins."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.registry import InMemoryAgentRegistry
from app.domain.enums import Capability
from app.orchestration.selection import AgentSelector, UnknownAgentsError
from app.providers.fake import FAKE_MODELS
from app.schemas.workflow import TaskRequest
from app.services.model_pins import pin_model


async def test_exact_agent_ids_force_the_roster() -> None:
    selector = AgentSelector(InMemoryAgentRegistry(list(BUILTIN_AGENTS)))
    required = frozenset({Capability.VULNERABILITY_ANALYSIS})

    result = await selector.select(
        required, agent_ids=frozenset({"security-agent", "documentation-agent"})
    )

    assert set(result.agent_ids) == {"documentation-agent", "security-agent"}
    assert "coding-agent" in result.excluded
    assert "not included" in result.excluded["coding-agent"]


async def test_unknown_agent_id_is_rejected() -> None:
    selector = AgentSelector(InMemoryAgentRegistry(list(BUILTIN_AGENTS)))

    with pytest.raises(UnknownAgentsError, match="ghost-agent"):
        await selector.select(
            frozenset({Capability.DOCUMENTATION}),
            agent_ids=frozenset({"ghost-agent"}),
        )


def test_pin_model_updates_preference() -> None:
    agent = next(a for a in BUILTIN_AGENTS if a.id == "coding-agent")
    pinned = pin_model(agent, "fake:cheap")

    assert pinned.model_preference.preferred_model == "fake:cheap"
    assert pinned.model_preference.preferred_provider == "fake"


def test_task_request_rejects_empty_agent_ids() -> None:
    with pytest.raises(ValidationError):
        TaskRequest(request="Audit the repo", agent_ids=[])


async def test_submit_with_agent_and_model_override(db_client: AsyncClient) -> None:
    cheap = FAKE_MODELS[1].id
    response = await db_client.post(
        "/api/v1/tasks?wait=true",
        json={
            "request": "Find security vulnerabilities in the payments service",
            "agent_ids": ["security-agent"],
            "model_overrides": {"security-agent": cheap},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [node["agent_id"] for node in body["nodes"]] == ["security-agent"]
    assert body["nodes"][0]["agent_name"] == "Security Agent"
    assert any(
        execution.get("model") == cheap
        for node in body["nodes"]
        for execution in node.get("executions", [])
    )


async def test_one_model_routing_pins_every_node(db_client: AsyncClient) -> None:
    shared = FAKE_MODELS[0].id
    response = await db_client.post(
        "/api/v1/tasks?wait=true",
        json={
            "request": "Find security vulnerabilities in the payments service",
            "agent_ids": ["security-agent"],
            "routing_strategy": "one",
            "shared_model": shared,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(
        execution.get("model") == shared
        for node in body["nodes"]
        for execution in node.get("executions", [])
    )


async def test_mixed_routing_requires_overrides() -> None:
    with pytest.raises(ValidationError, match="model_overrides"):
        TaskRequest(
            request="Audit the repo carefully please",
            routing_strategy="mixed",
        )


async def test_agent_fixed_binding_round_trip(db_client: AsyncClient) -> None:
    model_id = FAKE_MODELS[0].id
    pinned = await db_client.patch(
        "/api/v1/agents/coding-agent/model-binding",
        json={"preferred_model": model_id},
    )
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["model_strategy"] == "fixed"
    assert pinned.json()["preferred_model"] == model_id

    cleared = await db_client.patch(
        "/api/v1/agents/coding-agent/model-binding",
        json={"preferred_model": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["model_strategy"] == "auto"
    assert cleared.json()["preferred_model"] is None


async def test_unknown_model_override_is_a_422(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/tasks?wait=false",
        json={
            "request": "Find security vulnerabilities",
            "model_overrides": {"security-agent": "nowhere:imaginary"},
        },
    )

    assert response.status_code == 422
    assert "unknown or unconfigured models" in response.json()["detail"]


async def test_plan_preview_respects_agent_ids(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/tasks/plan",
        json={
            "request": "Audit this repository, fix what you find, and document the changes",
            "agent_ids": ["security-agent", "documentation-agent"],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert {node["agent_id"] for node in body["nodes"]} == {
        "security-agent",
        "documentation-agent",
    }
