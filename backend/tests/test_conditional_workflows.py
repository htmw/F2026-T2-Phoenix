"""Conditional execution: skipping work that is not needed, and saying why.

The headline case is from the product brief: when the security agent finds nothing, the
coding agent must not run. These tests hold that behaviour to the letter, including the
part that is easy to forget — the report still runs, and the skip carries an explanation.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.registry import DatabaseAgentRegistry, InMemoryAgentRegistry
from app.domain.enums import Capability, NodeStatus, WorkflowStatus
from app.orchestration.capability_analysis import CapabilityAnalysis
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import AgentSelector
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.workflow import (
    EdgeCondition,
    TaskRequest,
    WorkflowEdge,
    WorkflowNode,
    WorkflowPlan,
)
from app.services.agent_executor import AgentExecutor
from app.services.workflow_repository import WorkflowRepository
from app.workflows.conditions import describe, evaluate, resolve_path
from app.workflows.engine import WorkflowEngine, WorkflowRun


def engine_for(session: AsyncSession, provider: FakeProvider) -> WorkflowEngine:
    return WorkflowEngine(
        DatabaseAgentRegistry(session),
        AgentExecutor(ProviderRegistry([provider])),
        WorkflowRepository(session),
    )


async def run_plan(
    session: AsyncSession, provider: FakeProvider, plan: WorkflowPlan
) -> tuple[WorkflowRun, WorkflowRepository]:
    repository = WorkflowRepository(session)
    task = await repository.create_task(TaskRequest(request="Audit and fix this repository"))
    workflow = await repository.create_workflow(task.id, plan)
    run = await engine_for(session, provider).run(workflow.id, task.id, plan)
    return run, repository


def audit_then_fix_plan(*, with_report: bool = True) -> WorkflowPlan:
    """security → coding (only if findings) → report."""
    nodes = [
        WorkflowNode(key="security", agent_id="security-agent", objective="Audit the repo"),
        WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix the findings"),
    ]
    edges = [
        WorkflowEdge(
            source="security",
            target="coding",
            condition=EdgeCondition(
                path="findings",
                operator="non_empty",
                description="the security agent reported no findings",
            ),
        )
    ]
    if with_report:
        nodes.append(
            WorkflowNode(
                key="documentation",
                agent_id="documentation-agent",
                objective="Report on the work",
                join_policy="any",
            )
        )
        edges += [
            WorkflowEdge(source="security", target="documentation"),
            WorkflowEdge(source="coding", target="documentation"),
        ]
    return WorkflowPlan(nodes=tuple(nodes), edges=tuple(edges))


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("operator", "value", "payload", "expected"),
    [
        ("non_empty", None, {"findings": [1]}, True),
        ("non_empty", None, {"findings": []}, False),
        ("non_empty", None, {}, False),
        ("empty", None, {"findings": []}, True),
        ("empty", None, {}, True),
        ("exists", None, {"findings": []}, True),
        ("not_exists", None, {}, True),
        ("is_true", None, {"findings": True}, True),
        ("is_false", None, {"findings": False}, True),
        ("is_false", None, {}, False),
        ("eq", 3, {"findings": 3}, True),
        ("ne", 3, {"findings": 4}, True),
        ("gt", 2, {"findings": 3}, True),
        ("gte", 3, {"findings": 3}, True),
        ("lt", 2, {"findings": 1}, True),
        ("lte", 1, {"findings": 1}, True),
        ("contains", "cipher", {"findings": "weak cipher"}, True),
        ("contains", "x", {"findings": ["x"]}, True),
    ],
)
def test_operators(
    operator: Any, value: object, payload: dict[str, object], expected: bool
) -> None:
    condition = EdgeCondition(path="findings", operator=operator, value=value)
    assert evaluate(condition, payload) is expected


def test_missing_path_is_an_answer_not_an_error() -> None:
    # A model omitting an optional field is normal. Raising here would fail runs for a
    # reason the user cannot act on.
    condition = EdgeCondition(path="a.b.c", operator="exists")
    assert evaluate(condition, {"a": {"b": {}}}) is False


def test_conditions_can_read_into_arrays() -> None:
    payload = {"findings": [{"severity": "high"}, {"severity": "low"}]}
    assert resolve_path(payload, "findings.0.severity") == "high"
    assert evaluate(EdgeCondition(path="findings.0.severity", operator="eq", value="high"), payload)


def test_is_false_ignores_a_missing_field() -> None:
    # Treating an omission as a denial would skip work on the strength of silence.
    assert evaluate(EdgeCondition(path="passed", operator="is_false"), {}) is False


def test_mistyped_comparison_does_not_blow_up_the_run() -> None:
    condition = EdgeCondition(path="count", operator="gt", value=3)
    assert evaluate(condition, {"count": "many"}) is False


def test_description_is_preferred_over_a_generated_reason() -> None:
    condition = EdgeCondition(
        path="findings", operator="non_empty", description="nothing was found"
    )
    assert describe(condition, "security") == "nothing was found"
    generated = describe(EdgeCondition(path="findings", operator="non_empty"), "security")
    assert "security" in generated and "findings" in generated


# ---------------------------------------------------------------------------
# The product's headline case
# ---------------------------------------------------------------------------


async def test_no_findings_means_the_coding_agent_never_runs(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": []})  # a clean audit
    provider.queue_json({"document": "# Report", "format": "markdown"})

    run, repository = await run_plan(seeded_session, provider, audit_then_fix_plan())
    await seeded_session.commit()

    assert run.status is WorkflowStatus.COMPLETED
    assert "coding" not in run.outputs
    assert "coding" in run.skipped
    # Two calls, not three: the skipped agent cost nothing, which is the point.
    assert len(provider.requests) == 2


async def test_a_skip_is_recorded_with_a_reason(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": []})
    provider.queue_json({"document": "# Report", "format": "markdown"})

    _, repository = await run_plan(seeded_session, provider, audit_then_fix_plan())
    await seeded_session.commit()

    workflow = (await repository.list_workflows())[0]
    coding = next(node for node in workflow.nodes if node.node_key == "coding")

    assert coding.status == NodeStatus.SKIPPED
    # A node showing "skipped" with no explanation reads as a bug.
    assert coding.skip_reason is not None
    assert "findings" in coding.skip_reason


async def test_findings_mean_the_coding_agent_does_run(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": [{"severity": "high", "issue": "SQL injection"}]})
    provider.queue_json({"changes": [{"file": "db.py", "action": "modify"}]})
    provider.queue_json({"document": "# Report", "format": "markdown"})

    run, _ = await run_plan(seeded_session, provider, audit_then_fix_plan())

    assert run.status is WorkflowStatus.COMPLETED
    assert "coding" in run.outputs
    assert run.skipped == {}


async def test_the_report_still_runs_when_a_branch_is_skipped(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": []})
    provider.queue_json({"document": "# Report", "format": "markdown"})

    run, _ = await run_plan(seeded_session, provider, audit_then_fix_plan())

    # A reporting node joins on "any": it should describe the audit that did happen
    # rather than disappear because the fix was unnecessary.
    assert "documentation" in run.outputs


async def test_a_skipped_branch_is_reported_in_the_final_result(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": []})
    provider.queue_json({"document": "# Report", "format": "markdown"})

    _, repository = await run_plan(seeded_session, provider, audit_then_fix_plan())
    await seeded_session.commit()

    workflow = (await repository.list_workflows())[0]
    # "This agent was not needed, and here is why" is part of the answer.
    assert "coding" in workflow.final_result["skipped"]


async def test_skip_propagates_down_a_chain(seeded_session: AsyncSession) -> None:
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix"),
            WorkflowNode(key="testing", agent_id="testing-agent", objective="Test the fix"),
        ),
        edges=(
            WorkflowEdge(
                source="security",
                target="coding",
                condition=EdgeCondition(path="findings", operator="non_empty"),
            ),
            WorkflowEdge(source="coding", target="testing"),
        ),
    )
    provider = FakeProvider()
    provider.queue_json({"findings": []})

    run, repository = await run_plan(seeded_session, provider, plan)
    await seeded_session.commit()

    # Testing a fix that was never made is meaningless, so the skip carries downstream.
    assert set(run.skipped) == {"coding", "testing"}
    assert run.status is WorkflowStatus.COMPLETED
    assert len(provider.requests) == 1

    workflow = (await repository.list_workflows())[0]
    testing = next(node for node in workflow.nodes if node.node_key == "testing")
    assert testing.status == NodeStatus.SKIPPED
    assert "coding" in (testing.skip_reason or "")


async def test_all_join_waits_for_every_branch_to_be_satisfied(
    seeded_session: AsyncSession,
) -> None:
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="research", agent_id="research-agent", objective="Research"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix", join_policy="all"),
        ),
        edges=(
            WorkflowEdge(
                source="security",
                target="coding",
                condition=EdgeCondition(path="findings", operator="non_empty"),
            ),
            WorkflowEdge(source="research", target="coding"),
        ),
    )
    provider = FakeProvider()
    provider.queue_json({"findings": []})
    provider.queue_json({"findings": ["best practice X"]})

    run, _ = await run_plan(seeded_session, provider, plan)

    # One unsatisfied edge is enough under "all": the fix has nothing to act on.
    assert "coding" in run.skipped


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


async def test_planner_guards_the_coding_agent_behind_findings() -> None:
    registry = InMemoryAgentRegistry(list(BUILTIN_AGENTS))
    required = frozenset({Capability.VULNERABILITY_ANALYSIS, Capability.CODE_MODIFICATION})
    selection = await AgentSelector(registry).select(required)
    analysis = CapabilityAnalysis(required=required, reasoning="test", source="test")

    plan = WorkflowPlanner().plan("Audit and fix", analysis, selection)
    edge = next(edge for edge in plan.edges if edge.target == "coding")

    # Stated once over capabilities, so it holds for any agent providing them.
    assert edge.condition is not None
    assert edge.condition.path == "findings"
    assert edge.condition.operator == "non_empty"


async def test_planner_marks_a_reporting_node_as_an_any_join() -> None:
    registry = InMemoryAgentRegistry(list(BUILTIN_AGENTS))
    required = frozenset(
        {
            Capability.VULNERABILITY_ANALYSIS,
            Capability.CODE_MODIFICATION,
            Capability.REPORT_GENERATION,
        }
    )
    selection = await AgentSelector(registry).select(required)
    analysis = CapabilityAnalysis(required=required, reasoning="test", source="test")

    plan = WorkflowPlanner().plan("Audit, fix, and report", analysis, selection)

    assert plan.node("documentation").join_policy == "any"
    assert plan.node("coding").join_policy == "all"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


async def test_skipped_nodes_are_visible_in_the_api(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json({"findings": []})
    fake_provider.queue_json({"document": "# Report", "format": "markdown"})

    response = await db_client.post(
        "/api/v1/tasks",
        json={"request": "Audit this repository for vulnerabilities and fix what you find"},
    )

    assert response.status_code == 200
    body = response.json()
    coding = next(node for node in body["nodes"] if node["key"] == "coding")

    assert coding["status"] == NodeStatus.SKIPPED.value
    assert coding["skip_reason"]
    assert body["status"] == WorkflowStatus.COMPLETED.value


async def test_conditions_are_visible_on_the_planned_graph(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/tasks/plan",
        json={"request": "Audit this repository for vulnerabilities and fix what you find"},
    )

    assert response.status_code == 200
    edges = response.json()["edges"]
    # The plan preview is how a user decides whether to spend money, so a conditional
    # edge has to be visible before the run, not only after.
    assert any(edge["source"] == "security" and edge["target"] == "coding" for edge in edges)
