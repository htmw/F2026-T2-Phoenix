"""Human approval, operator controls, and honest result synthesis."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.registry import InMemoryAgentRegistry
from app.domain.enums import Capability, ErrorKind, ExecutionStatus, NodeStatus, WorkflowStatus
from app.orchestration.capability_analysis import CapabilityAnalysis
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import AgentSelector
from app.providers.fake import FakeProvider
from app.schemas.execution import AgentOutput
from app.schemas.workflow import TaskRequest, WorkflowEdge, WorkflowNode, WorkflowPlan
from app.services.orchestration_service import NodeControlError
from app.services.workflow_repository import WorkflowRepository
from app.workflows.synthesis import synthesise
from tests.test_retry_and_recovery import run_plan, service_for


def gated_code_then_test() -> WorkflowPlan:
    return WorkflowPlan(
        nodes=(
            WorkflowNode(
                key="coding",
                agent_id="coding-agent",
                objective="Write the feature",
                requires_approval=True,
            ),
            WorkflowNode(key="testing", agent_id="testing-agent", objective="Test the change"),
        ),
        edges=(WorkflowEdge(source="coding", target="testing"),),
    )


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


async def test_a_gated_node_pauses_before_it_runs(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json({"changes": [{"file": "app.py", "action": "modify"}]})

    run, repository, workflow_id = await run_plan(seeded_session, provider, gated_code_then_test())
    await seeded_session.commit()

    assert run.status is WorkflowStatus.AWAITING_APPROVAL
    assert provider.requests == []

    workflow = await repository.get_workflow(workflow_id)
    nodes = {node.node_key: node for node in workflow.nodes}
    assert nodes["coding"].status == NodeStatus.AWAITING_APPROVAL
    assert nodes["testing"].status == NodeStatus.WAITING


async def test_approving_a_gate_runs_the_node_and_everything_after(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    run, _, workflow_id = await run_plan(seeded_session, provider, gated_code_then_test())
    await seeded_session.commit()
    assert run.status is WorkflowStatus.AWAITING_APPROVAL

    resumed_provider = FakeProvider()
    resumed_provider.queue_json({"changes": [{"file": "app.py", "action": "modify"}]})
    resumed_provider.queue_json({"passed": True, "tests": [{"name": "test_feature"}]})

    result = await service_for(seeded_session, resumed_provider).approve_node(
        workflow_id, "coding", decided_by="alice", reason="looks safe"
    )
    await seeded_session.commit()

    assert result.run.status is WorkflowStatus.COMPLETED
    assert "coding" in result.run.outputs
    assert "testing" in result.run.outputs
    coding = next(node for node in result.workflow.nodes if node.node_key == "coding")
    approval = coding.approval
    assert approval is not None
    assert approval["approved"] is True
    assert approval["decided_by"] == "alice"


async def test_rejecting_a_gate_skips_the_branch(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    _, _, workflow_id = await run_plan(seeded_session, provider, gated_code_then_test())
    await seeded_session.commit()

    result = await service_for(seeded_session, FakeProvider()).reject_node(
        workflow_id, "coding", decided_by="bob", reason="too risky"
    )
    await seeded_session.commit()

    assert result.run.status is WorkflowStatus.COMPLETED
    assert "coding" in result.run.skipped
    assert "testing" in result.run.skipped
    assert result.run.outputs == {}


async def test_planner_gates_code_work_when_approval_is_required() -> None:
    registry = InMemoryAgentRegistry(list(BUILTIN_AGENTS))
    required = frozenset({Capability.CODE_MODIFICATION, Capability.TEST_GENERATION})
    selection = await AgentSelector(registry).select(required)
    analysis = CapabilityAnalysis(required=required, reasoning="test", source="test")

    gated = WorkflowPlanner().plan("Fix and test", analysis, selection, require_approval=True)
    ungated = WorkflowPlanner().plan("Fix and test", analysis, selection, require_approval=False)

    assert gated.node("coding").requires_approval is True
    assert gated.node("testing").requires_approval is False
    assert ungated.node("coding").requires_approval is False


# ---------------------------------------------------------------------------
# Retry / skip
# ---------------------------------------------------------------------------


async def test_retrying_a_failed_node_reruns_it_and_downstream(
    seeded_session: AsyncSession,
) -> None:
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Write"),
            WorkflowNode(key="testing", agent_id="testing-agent", objective="Test"),
        ),
        edges=(WorkflowEdge(source="coding", target="testing"),),
    )
    fail_provider = FakeProvider()
    fail_provider.queue_failure(ErrorKind.AUTHENTICATION, "bad key")
    _, _, workflow_id = await run_plan(seeded_session, fail_provider, plan)
    await seeded_session.commit()

    retry_provider = FakeProvider()
    retry_provider.queue_json({"changes": [{"file": "app.py", "action": "modify"}]})
    retry_provider.queue_json({"passed": True})
    result = await service_for(seeded_session, retry_provider).retry_node(workflow_id, "coding")

    assert result.run.status is WorkflowStatus.COMPLETED
    assert len(retry_provider.requests) == 2
    assert result.run.outputs["testing"].payload["passed"] is True


async def test_skipping_a_failed_node_lets_the_workflow_finish(
    seeded_session: AsyncSession,
) -> None:
    plan = WorkflowPlan(
        nodes=(WorkflowNode(key="coding", agent_id="coding-agent", objective="Write"),)
    )
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.AUTHENTICATION, "bad key")
    _, _, workflow_id = await run_plan(seeded_session, provider, plan)
    await seeded_session.commit()

    result = await service_for(seeded_session, FakeProvider()).skip_node(
        workflow_id, "coding", reason="operator will handle this"
    )

    assert result.run.status is WorkflowStatus.COMPLETED
    assert result.run.skipped["coding"] == "operator will handle this"


async def test_a_running_workflow_refuses_node_controls(seeded_session: AsyncSession) -> None:
    repository = WorkflowRepository(seeded_session)
    task = await repository.create_task(TaskRequest(request="Fix it"))
    plan = WorkflowPlan(
        nodes=(WorkflowNode(key="coding", agent_id="coding-agent", objective="Write"),)
    )
    workflow = await repository.create_workflow(task.id, plan)
    await repository.start_workflow(workflow.id)
    await seeded_session.commit()

    try:
        await service_for(seeded_session, FakeProvider()).skip_node(workflow.id, "coding")
    except NodeControlError as exc:
        assert "running" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("controls must not race a live run")


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def test_synthesis_prefers_a_documentation_agent_and_lists_skips() -> None:
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(
                key="coding",
                agent_id="coding-agent",
                objective="Fix",
            ),
            WorkflowNode(
                key="documentation",
                agent_id="documentation-agent",
                objective="Write it up",
                join_policy="any",
            ),
        ),
        edges=(
            WorkflowEdge(
                source="security",
                target="coding",
            ),
            WorkflowEdge(source="security", target="documentation"),
            WorkflowEdge(source="coding", target="documentation"),
        ),
    )
    # The engine's skip path is tested elsewhere; this checks the assembled answer
    # names everyone who contributed and does not pretend the skipped work happened.
    outputs = {
        "security": AgentOutput(
            agent_id="security-agent",
            node_key="security",
            status=ExecutionStatus.SUCCEEDED,
            payload={"findings": []},
            summary="No issues.",
        ),
        "documentation": AgentOutput(
            agent_id="documentation-agent",
            node_key="documentation",
            status=ExecutionStatus.SUCCEEDED,
            payload={"document": "# Audit\nNothing to fix.", "format": "markdown"},
            summary="Wrote the report.",
        ),
    }
    result = synthesise(plan, outputs, {"coding": "no findings to fix"}, total_cost_usd=0.12)

    assert result["answer"] == "# Audit\nNothing to fix."
    assert result["partial"] is True
    assert result["skipped"] == {"coding": "no findings to fix"}
    contributors = result["contributors"]
    assert isinstance(contributors, list)
    assert {item["agent_id"] for item in contributors if isinstance(item, dict)} == {
        "security-agent",
        "documentation-agent",
    }


def test_synthesis_returns_full_answer_not_just_summary() -> None:
    plan = WorkflowPlan(
        nodes=(WorkflowNode(key="general", agent_id="general-agent", objective="Write code"),),
        edges=(),
    )
    outputs = {
        "general": AgentOutput(
            agent_id="general-agent",
            node_key="general",
            status=ExecutionStatus.SUCCEEDED,
            payload={
                "summary": "Provided Python code.",
                "answer": "```python\nprint(1)\n```",
                "artifacts": [
                    {"name": "main.py", "kind": "code", "content": "print(1)\n"},
                ],
            },
            summary="Provided Python code.",
        ),
    }
    result = synthesise(plan, outputs, {}, total_cost_usd=0.01)
    assert "print(1)" in str(result["answer"])
    assert result["answer"] != "Provided Python code."


def test_synthesis_formats_coding_file_contents() -> None:
    plan = WorkflowPlan(
        nodes=(WorkflowNode(key="coding", agent_id="coding-agent", objective="Write file"),),
        edges=(),
    )
    outputs = {
        "coding": AgentOutput(
            agent_id="coding-agent",
            node_key="coding",
            status=ExecutionStatus.SUCCEEDED,
            payload={
                "summary": "Created fibonacci.py",
                "changes": [
                    {
                        "file": "fibonacci.py",
                        "action": "create",
                        "content": "def fib(n):\n    return n\n",
                    }
                ],
            },
            summary="Created fibonacci.py",
        ),
    }
    result = synthesise(plan, outputs, {}, total_cost_usd=0.02)
    answer = str(result["answer"])
    assert "fibonacci.py" in answer
    assert "def fib(n):" in answer


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


async def test_approve_endpoint_resumes_a_paused_workflow(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    submitted = await db_client.post(
        "/api/v1/tasks",
        json={"request": "Fix the login handler", "require_approval": True},
    )
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["status"] == WorkflowStatus.AWAITING_APPROVAL.value
    coding = next(node for node in body["nodes"] if node["agent_id"] == "coding-agent")
    assert coding["status"] == NodeStatus.AWAITING_APPROVAL.value
    assert coding["requires_approval"] is True

    fake_provider.queue_json({"changes": [{"file": "login.py", "action": "modify"}]})
    approved = await db_client.post(
        f"/api/v1/workflows/{body['id']}/nodes/{coding['key']}/approve",
        json={"decided_by": "alice", "reason": "go ahead"},
    )
    assert approved.status_code == 200
    finished = approved.json()
    assert finished["status"] == WorkflowStatus.COMPLETED.value
    # Body decided_by is ignored; operator identity wins.
    assert finished["nodes"][0]["approval"]["decided_by"] == "test-operator"
    assert finished["final_result"]["contributors"]


async def test_reject_endpoint_records_the_decision(
    db_client: AsyncClient,
) -> None:
    submitted = await db_client.post(
        "/api/v1/tasks",
        json={"request": "Fix the login handler", "require_approval": True},
    )
    workflow_id = submitted.json()["id"]
    node_key = next(
        node["key"] for node in submitted.json()["nodes"] if node["agent_id"] == "coding-agent"
    )

    rejected = await db_client.post(
        f"/api/v1/workflows/{workflow_id}/nodes/{node_key}/reject",
        json={"decided_by": "bob", "reason": "too risky"},
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["status"] == WorkflowStatus.COMPLETED.value
    coding = next(node for node in body["nodes"] if node["key"] == node_key)
    assert coding["status"] == NodeStatus.SKIPPED.value
    assert coding["skip_reason"] == "too risky"


async def test_retry_endpoint_recovers_a_failed_agent(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_failure(ErrorKind.AUTHENTICATION, "bad key")
    submitted = await db_client.post("/api/v1/tasks", json={"request": "Fix the login handler"})
    assert submitted.json()["status"] == WorkflowStatus.FAILED.value
    node_key = submitted.json()["nodes"][0]["key"]

    fake_provider.queue_json({"changes": [{"file": "login.py", "action": "modify"}]})
    retried = await db_client.post(
        f"/api/v1/workflows/{submitted.json()['id']}/nodes/{node_key}/retry"
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == WorkflowStatus.COMPLETED.value


async def test_skip_endpoint_404s_for_an_unknown_node(db_client: AsyncClient) -> None:
    submitted = await db_client.post("/api/v1/tasks", json={"request": "Fix the login handler"})
    response = await db_client.post(
        f"/api/v1/workflows/{submitted.json()['id']}/nodes/not-a-node/skip"
    )
    assert response.status_code == 404


async def test_control_on_an_unknown_workflow_is_404(db_client: AsyncClient) -> None:
    response = await db_client.post(
        f"/api/v1/workflows/{uuid.uuid4()}/nodes/coding/approve",
        json={"decided_by": "alice"},
    )
    assert response.status_code == 404
