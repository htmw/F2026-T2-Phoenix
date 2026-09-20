"""Level 3 generative teams: design a bespoke team per request, then run it.

Covers the end-to-end endpoint, the hard team-size cap, the fallback to a default team,
and the compiler's cost/model guardrails.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.orchestration.team_designer import build_team
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.team import TeamAgentSpec, TeamSpec

_DESIGN = {
    "domain": "research",
    "reasoning": "gather facts, then write them up",
    "agents": [
        {"role": "Researcher", "objective": "Gather the facts.", "depends_on": [], "is_synthesizer": False},
        {
            "role": "Report Writer",
            "objective": "Write the summary.",
            "depends_on": ["Researcher"],
            "is_synthesizer": True,
        },
    ],
}


async def test_generative_designs_and_runs_a_team(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json(_DESIGN)  # consumed by the team designer's call

    response = await db_client.post(
        "/api/v1/tasks/generative",
        json={"request": "Research the coffee market and write a short summary."},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "completed"
    keys = [node["key"] for node in body["nodes"]]
    assert keys == ["researcher", "report-writer"]
    assert all(node["agent_id"].startswith("gen-") for node in body["nodes"])
    # The synthesizer joins over the specialist and writes the final document.
    assert ("researcher", "report-writer") in [(e["source"], e["target"]) for e in body["edges"]]
    writer = next(n for n in body["nodes"] if n["key"] == "report-writer")
    assert writer["join_policy"] == "any"


async def test_generative_team_is_capped_below_five(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    # The model over-designs: six specialists plus a synthesizer. The cap must hold.
    oversized = {
        "domain": "big",
        "reasoning": "too many",
        "agents": [
            {"role": f"Specialist {i}", "objective": f"Do part {i}.", "depends_on": []}
            for i in range(6)
        ]
        + [{"role": "Synth", "objective": "Combine.", "depends_on": [], "is_synthesizer": True}],
    }
    fake_provider.queue_json(oversized)

    response = await db_client.post(
        "/api/v1/tasks/generative", json={"request": "Do a big multi-part analysis."}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert len(body["nodes"]) <= 4  # generative_max_agents


async def test_generative_falls_back_to_a_default_team(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    # A design the parser cannot use degrades to the fixed default team, not an error.
    fake_provider.queue_json({"not": "a team"})

    response = await db_client.post(
        "/api/v1/tasks/generative", json={"request": "Something the designer cannot parse."}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    keys = [node["key"] for node in body["nodes"]]
    assert "synthesizer" in keys
    assert 2 <= len(keys) <= 4


def test_build_team_pins_cheapest_model_and_splits_budget() -> None:
    providers = ProviderRegistry([FakeProvider()])
    cheapest = min(
        providers.available_models(),
        key=lambda m: (m.output_cost_per_million, m.input_cost_per_million, m.id),
    )
    spec = TeamSpec(
        domain="test",
        reasoning="two agents",
        agents=(
            TeamAgentSpec(role="Worker", objective="do work"),
            TeamAgentSpec(
                role="Synthesizer", objective="combine", depends_on=("Worker",), is_synthesizer=True
            ),
        ),
    )

    agents, plan = build_team("a request", spec, providers=providers, budget_usd=0.40)

    assert len(agents) == 2
    for agent in agents:
        assert agent.id.startswith("gen-")
        assert agent.model_preference.preferred_model == cheapest.id
        # Equal slice of the $0.40 budget: each agent's own hard ceiling.
        assert agent.limits.max_cost_usd == 0.20
    assert len(plan.nodes) == 2
