"""Capability analysis, agent selection, and planning.

The product claim under test: the right agents run, the wrong ones do not, and the
reason for each decision is recorded.
"""

from __future__ import annotations

import pytest

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.registry import InMemoryAgentRegistry
from app.domain.enums import Capability, ErrorKind
from app.orchestration.capability_analysis import (
    CapabilityAnalysis,
    HeuristicCapabilityAnalyser,
    LLMCapabilityAnalyser,
)
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import (
    AgentSelector,
    NoAgentForCapabilityError,
    SelectionResult,
)
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.workflow import WorkflowPlan
from tests.test_registry import make_definition

# ---------------------------------------------------------------------------
# Heuristic analysis
# ---------------------------------------------------------------------------


async def analyse(request: str) -> CapabilityAnalysis:
    return await HeuristicCapabilityAnalyser().analyse(request)


async def test_security_request_requires_vulnerability_analysis() -> None:
    result = await analyse("Review this repository for security vulnerabilities")

    assert Capability.VULNERABILITY_ANALYSIS in result.required


async def test_security_request_does_not_require_documentation() -> None:
    result = await analyse("Find SQL injection flaws in the payments service")

    # The core promise: unrelated agents are not activated.
    assert Capability.DOCUMENTATION not in result.required
    assert Capability.TEST_GENERATION not in result.required


async def test_documentation_request_requires_documentation() -> None:
    result = await analyse("Write a README documenting the public API")

    assert Capability.DOCUMENTATION in result.required


async def test_test_request_requires_test_generation() -> None:
    result = await analyse("Write unit tests for the auth module")

    assert Capability.TEST_GENERATION in result.required


async def test_narrow_request_does_not_require_planning() -> None:
    result = await analyse("Summarise this document")

    # Planning a single-step request is pure overhead.
    assert Capability.TASK_DECOMPOSITION not in result.required
    assert result.rejected[Capability.TASK_DECOMPOSITION]


async def test_broad_request_requires_planning() -> None:
    result = await analyse(
        "Analyse this repository for security vulnerabilities, fix them, "
        "write tests for the fixes, and document the changes"
    )

    assert Capability.TASK_DECOMPOSITION in result.required


async def test_multi_step_phrasing_triggers_planning() -> None:
    result = await analyse("Summarise the design and then implement it step by step")

    assert Capability.TASK_DECOMPOSITION in result.required


async def test_unclassifiable_request_still_gets_a_capability() -> None:
    result = await analyse("Tell me about the Peloponnesian War")

    # Refusing would be worse than answering on the General desk.
    assert result.required
    assert Capability.GENERAL_ASSISTANCE in result.required


async def test_analysis_explains_itself() -> None:
    result = await analyse("Find security vulnerabilities in this code")

    assert "security" in result.reasoning
    assert result.source == "heuristic"


async def test_analysis_records_why_capabilities_were_rejected() -> None:
    result = await analyse("Summarise this document")

    assert Capability.VULNERABILITY_ANALYSIS in result.rejected
    assert result.rejected[Capability.VULNERABILITY_ANALYSIS]


async def test_analysis_is_deterministic() -> None:
    request = "Audit dependencies and write a report"

    first = await analyse(request)
    second = await analyse(request)

    assert first.required == second.required


# ---------------------------------------------------------------------------
# LLM-backed analysis
# ---------------------------------------------------------------------------


def llm_analyser(provider: FakeProvider) -> LLMCapabilityAnalyser:
    return LLMCapabilityAnalyser(ProviderRegistry([provider]), HeuristicCapabilityAnalyser())


async def test_llm_analysis_uses_the_models_capabilities() -> None:
    provider = FakeProvider()
    provider.queue_json(
        {
            "capabilities": [Capability.CODE_REVIEW.value, Capability.DOCUMENTATION.value],
            "reasoning": "the request asks for a review and a write-up",
        }
    )

    result = await llm_analyser(provider).analyse("Look over my code and write it up")

    assert result.required == frozenset({Capability.CODE_REVIEW, Capability.DOCUMENTATION})
    assert result.source == "llm"
    assert "review" in result.reasoning


async def test_llm_analysis_drops_invented_capabilities() -> None:
    provider = FakeProvider()
    provider.queue_json({"capabilities": [Capability.CODE_REVIEW.value, "telepathy.mind_reading"]})

    result = await llm_analyser(provider).analyse("Review my code")

    # A hallucinated capability must not reach selection, where it would look like a
    # coverage gap and fail the request.
    assert result.required == frozenset({Capability.CODE_REVIEW})


async def test_llm_analysis_falls_back_when_the_provider_fails() -> None:
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.PROVIDER_UNAVAILABLE, "down")

    result = await llm_analyser(provider).analyse("Find security vulnerabilities")

    # A planning outage must not make the platform unusable.
    assert Capability.VULNERABILITY_ANALYSIS in result.required
    assert result.source == "llm->fallback"
    assert "provider error" in result.reasoning


async def test_llm_analysis_falls_back_on_unparseable_output() -> None:
    provider = FakeProvider(default_response="I'd rather not say.")

    result = await llm_analyser(provider).analyse("Write tests for the auth module")

    assert Capability.TEST_GENERATION in result.required
    assert result.source == "llm->fallback"


async def test_llm_analysis_falls_back_when_nothing_is_recognised() -> None:
    provider = FakeProvider()
    provider.queue_json({"capabilities": ["nonsense.one", "nonsense.two"]})

    result = await llm_analyser(provider).analyse("Document the API")

    assert Capability.DOCUMENTATION in result.required
    assert result.source == "llm->fallback"


async def test_llm_prompt_contains_the_capability_vocabulary() -> None:
    provider = FakeProvider()
    provider.queue_json({"capabilities": [Capability.CODE_REVIEW.value]})

    await llm_analyser(provider).analyse("Review my code")

    prompt = provider.requests[0].system_prompt
    for capability in Capability:
        assert capability.value in prompt


# ---------------------------------------------------------------------------
# Agent selection
# ---------------------------------------------------------------------------


@pytest.fixture
def selector() -> AgentSelector:
    return AgentSelector(InMemoryAgentRegistry(list(BUILTIN_AGENTS)))


async def test_selection_picks_the_agent_providing_the_capability(
    selector: AgentSelector,
) -> None:
    result = await selector.select(frozenset({Capability.VULNERABILITY_ANALYSIS}))

    assert result.agent_ids == ("security-agent",)


async def test_selection_excludes_every_other_agent_with_a_reason(
    selector: AgentSelector,
) -> None:
    result = await selector.select(frozenset({Capability.VULNERABILITY_ANALYSIS}))

    assert "coding-agent" in result.excluded
    assert "documentation-agent" in result.excluded
    assert all(reason for reason in result.excluded.values())


async def test_irrelevant_agent_is_excluded_as_irrelevant(selector: AgentSelector) -> None:
    result = await selector.select(frozenset({Capability.VULNERABILITY_ANALYSIS}))

    assert result.excluded["coding-agent"] == (
        "none of its capabilities are required by this request"
    )


async def test_redundant_agent_is_excluded_as_already_covered() -> None:
    # Two agents can do the same work; the reason must distinguish "redundant" from
    # "irrelevant", because they mean different things to someone reading the trace.
    registry = InMemoryAgentRegistry(
        [
            make_definition("writer-a", {Capability.DOCUMENTATION}),
            make_definition("writer-b", {Capability.DOCUMENTATION}),
        ]
    )

    result = await AgentSelector(registry).select(frozenset({Capability.DOCUMENTATION}))

    assert result.agent_ids == ("writer-a",)
    assert "already covered" in result.excluded["writer-b"]


async def test_one_agent_covering_several_capabilities_is_preferred(
    selector: AgentSelector,
) -> None:
    result = await selector.select(
        frozenset(
            {
                Capability.CODE_GENERATION,
                Capability.CODE_MODIFICATION,
                Capability.DEBUGGING,
            }
        )
    )

    # Three capabilities, one agent: fewer calls for the same coverage.
    assert result.agent_ids == ("coding-agent",)


async def test_selection_covers_capabilities_across_several_agents(
    selector: AgentSelector,
) -> None:
    result = await selector.select(
        frozenset({Capability.VULNERABILITY_ANALYSIS, Capability.DOCUMENTATION})
    )

    assert set(result.agent_ids) == {"security-agent", "documentation-agent"}


async def test_every_required_capability_is_attributed_to_an_agent(
    selector: AgentSelector,
) -> None:
    required = frozenset(
        {
            Capability.VULNERABILITY_ANALYSIS,
            Capability.CODE_MODIFICATION,
            Capability.TEST_GENERATION,
            Capability.DOCUMENTATION,
        }
    )

    result = await selector.select(required)

    covered = frozenset().union(*result.chosen.values())
    assert covered == required


async def test_uncovered_capability_is_refused_not_ignored() -> None:
    thin_registry = InMemoryAgentRegistry(
        [make_definition("only-agent", {Capability.DOCUMENTATION})]
    )

    with pytest.raises(NoAgentForCapabilityError) as caught:
        await AgentSelector(thin_registry).select(
            frozenset({Capability.DOCUMENTATION, Capability.VULNERABILITY_ANALYSIS})
        )

    # Silently answering a different question than asked would be worse than failing.
    assert Capability.VULNERABILITY_ANALYSIS in caught.value.uncovered


async def test_disabled_agent_is_not_selected() -> None:
    registry = InMemoryAgentRegistry(
        [
            make_definition("retired-agent", {Capability.DOCUMENTATION}).model_copy(
                update={"enabled": False}
            ),
            make_definition("live-agent", {Capability.DOCUMENTATION}),
        ]
    )

    result = await AgentSelector(registry).select(frozenset({Capability.DOCUMENTATION}))

    assert result.agent_ids == ("live-agent",)


async def test_selection_is_deterministic(selector: AgentSelector) -> None:
    required = frozenset({Capability.WEB_RESEARCH, Capability.DOCUMENTATION})

    picks = set()
    for _ in range(5):
        picks.add((await selector.select(required)).agent_ids)

    assert len(picks) == 1


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


async def plan_for(request: str) -> tuple[CapabilityAnalysis, SelectionResult, WorkflowPlan]:
    analysis = await analyse(request)
    selector = AgentSelector(InMemoryAgentRegistry(list(BUILTIN_AGENTS)))
    selection = await selector.select(analysis.required)
    plan = WorkflowPlanner().plan(request, analysis, selection)
    return analysis, selection, plan


async def test_plan_contains_one_node_per_selected_agent() -> None:
    _, selection, plan = await plan_for("Find security vulnerabilities in this repository")

    assert len(plan.nodes) == len(selection.chosen)


async def test_plan_orders_research_before_documentation() -> None:
    _, _, plan = await plan_for("Research the options and document the recommendation")

    keys = [node.key for node in plan.nodes]
    assert keys.index("research") < keys.index("documentation")


async def test_plan_orders_code_before_tests_before_review() -> None:
    _, _, plan = await plan_for(
        "Fix the failing test, write tests for the fix, and review the result"
    )

    keys = [node.key for node in plan.nodes]
    assert keys.index("coding") < keys.index("testing")
    assert keys.index("testing") < keys.index("review")


async def test_plan_puts_planning_first() -> None:
    _, _, plan = await plan_for(
        "Research the architecture, find security issues, fix them, test and document everything"
    )

    assert plan.nodes[0].key == "planning"


async def test_sequential_plan_is_a_single_chain() -> None:
    _, _, plan = await plan_for("Audit security and document the findings")

    nodes = plan.nodes
    edges = plan.edges
    assert len(edges) == len(nodes) - 1
    assert plan.roots() == (nodes[0].key,)


async def test_plan_records_the_selection_and_its_reasoning() -> None:
    analysis, _, plan = await plan_for("Find security vulnerabilities")

    selection = plan.selection
    assert selection is not None
    assert selection.reasoning == analysis.reasoning
    assert "documentation-agent" in selection.excluded


async def test_node_objective_repeats_the_users_words_verbatim() -> None:
    request = "Audit the payments-service repository for hardcoded credentials"
    _, _, plan = await plan_for(request)

    for node in plan.nodes:
        # A paraphrase drifts from what was asked, and every downstream agent inherits
        # the drift.
        assert request in node.objective


async def test_node_objective_states_the_agents_remit() -> None:
    _, _, plan = await plan_for("Find security vulnerabilities in this repository")

    node = plan.nodes[0]
    assert "Your remit" in node.objective
    assert Capability.VULNERABILITY_ANALYSIS.value in node.objective


async def test_planning_is_deterministic() -> None:
    request = "Audit security, fix the issues, and document them"

    first = await plan_for(request)
    second = await plan_for(request)

    assert [n.key for n in first[2].nodes] == [n.key for n in second[2].nodes]


def test_capability_vocabulary_is_fully_ranked() -> None:
    from app.orchestration.planner import _STAGE_RANKS

    # An unranked capability silently lands in the middle of the graph, which is a
    # subtle ordering bug rather than a visible failure.
    assert set(_STAGE_RANKS) == set(Capability)
