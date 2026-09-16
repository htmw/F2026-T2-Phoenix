"""Agent and capability API tests."""

from __future__ import annotations

from httpx import AsyncClient

from app.domain.enums import Capability


async def test_list_agents_returns_all_seeded_agents(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/agents")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 8
    assert {agent["id"] for agent in body} >= {
        "planning-agent",
        "security-agent",
        "general-agent",
    }


async def test_listed_agent_exposes_limits_and_capabilities(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/agents/coding-agent")

    assert response.status_code == 200
    agent = response.json()
    assert Capability.CODE_GENERATION.value in agent["capabilities"]
    assert agent["max_attempts"] == 3
    assert agent["max_cost_usd"] == 1.5
    assert agent["model_strategy"] == "auto"
    assert agent["preferred_provider"] is None
    assert agent["preferred_model"] is None
    assert agent["name"] == "Coding Agent"


async def test_builtin_agents_are_model_agnostic(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/agents")
    assert response.status_code == 200
    by_id = {agent["id"]: agent for agent in response.json()}

    assert by_id["security-agent"]["name"] == "Security Agent"
    assert by_id["security-agent"]["model_strategy"] == "auto"
    assert by_id["security-agent"]["preferred_model"] is None
    assert by_id["research-agent"]["preferred_provider"] is None
    assert by_id["documentation-agent"]["preferred_model"] is None
    assert by_id["general-agent"]["name"] == "General Agent"
    assert by_id["review-agent"]["name"] == "Review Agent"


async def test_agent_response_never_exposes_prompt_instructions(
    db_client: AsyncClient,
) -> None:
    response = await db_client.get("/api/v1/agents/security-agent")

    # Instructions are our prompt engineering, not part of the public contract.
    assert "instructions" not in response.json()


async def test_filtering_by_capability_narrows_the_list(db_client: AsyncClient) -> None:
    response = await db_client.get(
        "/api/v1/agents", params={"capability": Capability.VULNERABILITY_ANALYSIS.value}
    )

    assert response.status_code == 200
    assert [agent["id"] for agent in response.json()] == ["security-agent"]


async def test_filtering_by_an_unknown_capability_is_a_validation_error(
    db_client: AsyncClient,
) -> None:
    response = await db_client.get("/api/v1/agents", params={"capability": "not.a.capability"})

    assert response.status_code == 422


async def test_unknown_agent_returns_404(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/agents/ghost-agent")

    assert response.status_code == 404
    assert "ghost-agent" in response.json()["detail"]


async def test_agent_schema_endpoint_returns_contracts(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/agents/testing-agent/schema")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "testing-agent"
    assert body["output_schema"]["type"] == "object"
    assert "passed" in body["output_schema"]["properties"]


async def test_capability_catalogue_reports_coverage(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/capabilities")

    assert response.status_code == 200
    coverage = {entry["capability"]: entry for entry in response.json()}

    assert len(coverage) == len(Capability)
    assert coverage[Capability.CODE_GENERATION.value]["agent_ids"] == ["coding-agent"]
    assert coverage[Capability.CODE_GENERATION.value]["covered"] is True


async def test_every_capability_is_covered_by_a_builtin_agent(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/capabilities")

    uncovered = [entry["capability"] for entry in response.json() if not entry["covered"]]

    # A capability with no agent is a planning dead end, so the built-in set must span
    # the vocabulary it declares.
    assert uncovered == []


async def test_providers_mark_demo_mode(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/providers")
    assert response.status_code == 200
    body = response.json()
    fake = next((item for item in body if item["name"] == "fake"), None)
    assert fake is not None
    assert fake["demo"] is True
    assert "Demo" in fake["label"]
    assert all(model["demo"] is True for model in fake["models"])


async def test_providers_can_hide_demo(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/providers", params={"include_demo": False})
    assert response.status_code == 200
    assert all(item["name"] != "fake" for item in response.json())
    assert any(item["name"] == "openai" for item in response.json())