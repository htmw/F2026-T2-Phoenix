"""Parallel execution: fan-out, join, isolation, and bounded concurrency.

Wall-clock assertions use a provider that sleeps, so "concurrent" is measured rather
than assumed.
"""

from __future__ import annotations

import asyncio
import time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.registry import DatabaseAgentRegistry, InMemoryAgentRegistry
from app.domain.enums import Capability, ErrorKind, NodeStatus, WorkflowStatus
from app.orchestration.capability_analysis import CapabilityAnalysis
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import AgentSelector
from app.providers.base import CompletionRequest, CompletionResponse
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.workflow import TaskRequest, WorkflowEdge, WorkflowNode, WorkflowPlan
from app.services.agent_executor import AgentExecutor
from app.services.workflow_repository import WorkflowRepository
from app.workflows.engine import WorkflowEngine, WorkflowRun

NODE_DELAY = 0.20


class SlowFakeProvider(FakeProvider):
    """A provider with a measurable per-call delay, and a record of overlap."""

    def __init__(self, delay: float = NODE_DELAY) -> None:
        super().__init__()
        self._delay = delay
        self.in_flight = 0
        self.max_in_flight = 0

    async def generate(self, request: CompletionRequest) -> CompletionResponse:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self._delay)
            return await super().generate(request)
        finally:
            self.in_flight -= 1


def engine_for(
    session: AsyncSession, provider: FakeProvider, *, max_parallel: int = 4
) -> WorkflowEngine:
    return WorkflowEngine(
        DatabaseAgentRegistry(session),
        AgentExecutor(ProviderRegistry([provider])),
        WorkflowRepository(session),
        max_parallel_agents=max_parallel,
    )


def fan_out_plan() -> WorkflowPlan:
    """One root, three independent middle nodes, one join."""
    return WorkflowPlan(
        nodes=(
            WorkflowNode(key="planning", agent_id="planning-agent", objective="Plan the work"),
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="research", agent_id="research-agent", objective="Research"),
            WorkflowNode(key="testing", agent_id="testing-agent", objective="Write tests"),
            WorkflowNode(key="documentation", agent_id="documentation-agent", objective="Report"),
        ),
        edges=(
            WorkflowEdge(source="planning", target="security"),
            WorkflowEdge(source="planning", target="research"),
            WorkflowEdge(source="planning", target="testing"),
            WorkflowEdge(source="security", target="documentation"),
            WorkflowEdge(source="research", target="documentation"),
            WorkflowEdge(source="testing", target="documentation"),
        ),
    )


async def run_plan(
    session: AsyncSession,
    provider: FakeProvider,
    plan: WorkflowPlan,
    *,
    max_parallel: int = 4,
    budget_usd: float | None = None,
) -> tuple[WorkflowRun, WorkflowRepository]:
    repository = WorkflowRepository(session)
    task = await repository.create_task(TaskRequest(request="Do the work"))
    workflow = await repository.create_workflow(task.id, plan)
    run = await engine_for(session, provider, max_parallel=max_parallel).run(
        workflow.id, task.id, plan, budget_usd=budget_usd
    )
    return run, repository


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


async def test_independent_nodes_run_concurrently(seeded_session: AsyncSession) -> None:
    provider = SlowFakeProvider()
    plan = fan_out_plan()

    started = time.perf_counter()
    run, _ = await run_plan(seeded_session, provider, plan)
    elapsed = time.perf_counter() - started

    assert run.status is WorkflowStatus.COMPLETED
    # Five nodes at 0.2s each is 1.0s sequentially; three of them are independent, so
    # three stages of 0.2s is the floor. Allow generous slack for scheduling overhead.
    assert elapsed < 0.85, f"took {elapsed:.2f}s, expected roughly three stages"


async def test_siblings_actually_overlap(seeded_session: AsyncSession) -> None:
    provider = SlowFakeProvider()

    await run_plan(seeded_session, provider, fan_out_plan())

    # Three independent nodes must have been in flight together at some point.
    assert provider.max_in_flight == 3


async def test_sequential_plan_never_overlaps(seeded_session: AsyncSession) -> None:
    provider = SlowFakeProvider()
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix"),
        ),
        edges=(WorkflowEdge(source="security", target="coding"),),
    )

    await run_plan(seeded_session, provider, plan)

    assert provider.max_in_flight == 1


async def test_fan_out_respects_the_concurrency_limit(seeded_session: AsyncSession) -> None:
    provider = SlowFakeProvider()

    await run_plan(seeded_session, provider, fan_out_plan(), max_parallel=2)

    # The limit exists so a wide workflow cannot exhaust connections or trip a rate
    # limit that would fail every branch at once.
    assert provider.max_in_flight == 2


async def test_limit_of_one_serialises_execution(seeded_session: AsyncSession) -> None:
    provider = SlowFakeProvider()

    run, _ = await run_plan(seeded_session, provider, fan_out_plan(), max_parallel=1)

    assert provider.max_in_flight == 1
    assert run.status is WorkflowStatus.COMPLETED


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------


async def test_join_node_receives_every_upstream_result(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json({"steps": [{"description": "plan", "capability": "research.web"}]})
    provider.queue_json({"findings": [{"severity": "low", "issue": "Weak cipher"}]})
    provider.queue_json({"findings": ["Library X is unmaintained"]})
    provider.queue_json({"passed": True, "tests": [{"name": "test_login"}]})
    provider.queue_json({"document": "# Report", "format": "markdown"})

    await run_plan(seeded_session, provider, fan_out_plan())

    join_prompt = provider.requests[-1].user_prompt
    # All three branches must reach the join, or the report describes only part of the
    # work that was paid for.
    assert "Weak cipher" in join_prompt
    assert "Library X is unmaintained" in join_prompt
    assert "test_login" in join_prompt


async def test_join_waits_for_the_slowest_branch(seeded_session: AsyncSession) -> None:
    provider = SlowFakeProvider()

    run, repository = await run_plan(seeded_session, provider, fan_out_plan())
    await seeded_session.commit()

    assert set(run.outputs) == {
        "planning",
        "security",
        "research",
        "testing",
        "documentation",
    }


async def test_final_result_reports_the_join_only(seeded_session: AsyncSession) -> None:
    # No script: the fake provider answers each call with a stub shaped by that agent's
    # own schema, which is what lets a five-node graph succeed without hand-written
    # payloads per node.
    provider = FakeProvider()

    _, repository = await run_plan(seeded_session, provider, fan_out_plan())
    await seeded_session.commit()

    workflows = await repository.list_workflows()
    final = workflows[0].final_result
    # The join is the only terminal node, so it is the answer; branch payloads stay
    # available per node.
    assert list(final["nodes"]) == ["documentation"]
    assert len(final["agents_run"]) == 5


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


async def test_one_failing_branch_does_not_discard_its_siblings(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json({"steps": []})  # planning succeeds
    # Authentication failures are not retried, so this reliably kills one branch. Which
    # of the three siblings takes it depends on scheduling, and the assertions below do
    # not care.
    provider.queue_failure(ErrorKind.AUTHENTICATION, "invalid credentials")

    run, repository = await run_plan(seeded_session, provider, fan_out_plan())
    await seeded_session.commit()

    assert run.status is WorkflowStatus.FAILED

    workflow = (await repository.list_workflows())[0]
    statuses = {node.node_key: node.status for node in workflow.nodes}

    # Exactly one sibling failed; the other two kept their completed state and their
    # persisted results. Work that was paid for is not thrown away.
    assert statuses["planning"] == NodeStatus.COMPLETED
    failed = [key for key, status in statuses.items() if status == NodeStatus.FAILED]
    completed = [key for key, status in statuses.items() if status == NodeStatus.COMPLETED]
    assert len(failed) == 1
    assert len(completed) == 3  # planning plus the two surviving siblings


async def test_join_does_not_run_when_a_branch_fails(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json({"steps": []})
    provider.queue_failure(ErrorKind.AUTHENTICATION, "invalid credentials")

    run, _ = await run_plan(seeded_session, provider, fan_out_plan())

    # A report assembled from missing input would be confidently wrong.
    assert "documentation" not in run.outputs


async def test_sibling_costs_are_all_counted(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()

    run, repository = await run_plan(seeded_session, provider, fan_out_plan())
    await seeded_session.commit()

    per_node = sum(output.cost_usd for output in run.outputs.values())
    assert run.total_cost_usd == per_node
    assert await repository.workflow_cost(run.workflow_id) == per_node


# ---------------------------------------------------------------------------
# Planning parallel graphs
# ---------------------------------------------------------------------------


async def plan_for(
    capabilities: frozenset[Capability], *, sequential: bool = False
) -> WorkflowPlan:
    registry = InMemoryAgentRegistry(list(BUILTIN_AGENTS))
    selection = await AgentSelector(registry).select(capabilities)
    analysis = CapabilityAnalysis(required=capabilities, reasoning="test", source="test")
    return WorkflowPlanner(sequential=sequential).plan("Do the work", analysis, selection)


def targets_of(plan: WorkflowPlan, key: str) -> set[str]:
    return {edge.target for edge in plan.edges if edge.source == key}


async def test_planner_leaves_mutually_independent_agents_unconnected() -> None:
    plan = await plan_for(frozenset({Capability.VULNERABILITY_ANALYSIS, Capability.WEB_RESEARCH}))

    # A security audit reads the code; it does not consume research output. Ordering the
    # two would double the wall clock for no benefit.
    assert plan.edges == ()
    assert set(plan.roots()) == {"security", "research"}


async def test_planner_creates_a_diamond_for_a_wide_middle() -> None:
    plan = await plan_for(
        frozenset(
            {
                Capability.TASK_DECOMPOSITION,
                Capability.VULNERABILITY_ANALYSIS,
                Capability.TEST_GENERATION,
                Capability.DOCUMENTATION,
            }
        )
    )

    assert plan.roots() == ("planning",)
    # security and testing consume nothing from each other, so they fan out from
    # planning and rejoin at the report, which keeps every incoming edge.
    assert {"security", "testing"} <= targets_of(plan, "planning")
    assert set(plan.dependencies_of("documentation")) == {"planning", "security", "testing"}
    assert plan.dependencies_of("security") == ("planning",)
    assert plan.dependencies_of("testing") == ("planning",)


async def test_tests_and_review_run_alongside_each_other_after_coding() -> None:
    plan = await plan_for(
        frozenset(
            {
                Capability.VULNERABILITY_ANALYSIS,
                Capability.CODE_MODIFICATION,
                Capability.TEST_GENERATION,
                Capability.CODE_REVIEW,
            }
        )
    )

    # Both consume code changes and neither consumes the other, which is the shape the
    # product promises: fix, then test and review at the same time.
    assert targets_of(plan, "coding") == {"testing", "review"}
    assert plan.dependencies_of("testing") == ("coding",)
    assert plan.dependencies_of("review") == ("coding",)


async def test_planner_drops_dependencies_implied_by_others() -> None:
    plan = await plan_for(
        frozenset(
            {
                Capability.TASK_DECOMPOSITION,
                Capability.CODE_MODIFICATION,
                Capability.TEST_GENERATION,
            }
        )
    )

    # Coding already carries planning's output forward, so testing does not need a
    # shortcut edge from planning: that would only add tokens and cost.
    assert plan.dependencies_of("testing") == ("coding",)
    assert "planning" not in plan.dependencies_of("testing")


async def test_synthesis_keeps_every_incoming_edge() -> None:
    plan = await plan_for(
        frozenset(
            {
                Capability.VULNERABILITY_ANALYSIS,
                Capability.CODE_MODIFICATION,
                Capability.REPORT_GENERATION,
            }
        )
    )

    # A report that only saw the last branch would silently omit the audit.
    assert set(plan.dependencies_of("documentation")) == {"security", "coding"}


async def test_sequential_planner_still_produces_a_chain() -> None:
    plan = await plan_for(
        frozenset(
            {
                Capability.VULNERABILITY_ANALYSIS,
                Capability.TEST_GENERATION,
                Capability.DOCUMENTATION,
            }
        ),
        sequential=True,
    )

    assert len(plan.edges) == len(plan.nodes) - 1
    assert all(len(plan.dependencies_of(node.key)) <= 1 for node in plan.nodes)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


async def test_submitted_broad_request_runs_branches_in_parallel(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    response = await db_client.post(
        "/api/v1/tasks",
        json={
            "request": (
                "Research best practices, audit this repository for security "
                "vulnerabilities, write tests, and document everything"
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == WorkflowStatus.COMPLETED.value

    # The graph the user sees must show the parallelism: more than one node depends on
    # the same predecessor.
    by_source: dict[str, list[str]] = {}
    for edge in body["edges"]:
        by_source.setdefault(edge["source"], []).append(edge["target"])
    assert any(len(targets) > 1 for targets in by_source.values())
