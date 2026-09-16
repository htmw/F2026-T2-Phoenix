"""Workflow engine tests: sequencing, hand-off, persistence, and failure.

These run against real PostgreSQL with a scripted provider, so a multi-agent workflow is
executed for real — every node, every attempt, every row — without a network call.
"""

from __future__ import annotations

import json
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import DatabaseAgentRegistry
from app.domain.enums import ErrorKind, ExecutionStatus, NodeStatus, TaskStatus, WorkflowStatus
from app.models.workflow import ExecutionRecord, TaskRecord, WorkflowNodeRecord
from app.orchestration.capability_analysis import HeuristicCapabilityAnalyser
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import AgentSelector
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.workflow import TaskRequest, WorkflowEdge, WorkflowNode, WorkflowPlan
from app.services.agent_executor import AgentExecutor
from app.services.orchestration_service import OrchestrationService, UnservableRequestError
from app.services.workflow_repository import WorkflowRepository
from app.workflows.engine import WorkflowEngine

SECURITY_FINDINGS = {
    "findings": [{"severity": "high", "issue": "Hardcoded API key", "file": "config.py"}],
    "summary": "One high-severity finding.",
}
CODE_CHANGES = {
    "changes": [{"file": "config.py", "action": "modify", "content": "key = os.environ[...]"}],
    "summary": "Moved the key to an environment variable.",
}
DOCUMENT = {"document": "# Report\nOne issue found and fixed.", "format": "markdown"}


def engine_for(session: AsyncSession, provider: FakeProvider) -> WorkflowEngine:
    return WorkflowEngine(
        DatabaseAgentRegistry(session),
        AgentExecutor(ProviderRegistry([provider])),
        WorkflowRepository(session),
    )


def service_for(session: AsyncSession, provider: FakeProvider) -> OrchestrationService:
    repository = WorkflowRepository(session)
    registry = DatabaseAgentRegistry(session)
    return OrchestrationService(
        HeuristicCapabilityAnalyser(),
        AgentSelector(registry),
        WorkflowPlanner(),
        engine_for(session, provider),
        repository,
    )


def two_node_plan() -> WorkflowPlan:
    return WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit the repo"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix what was found"),
        ),
        edges=(WorkflowEdge(source="security", target="coding"),),
    )


# ---------------------------------------------------------------------------
# Sequential execution
# ---------------------------------------------------------------------------


async def test_nodes_run_in_dependency_order(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)

    run = await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    assert run.status is WorkflowStatus.COMPLETED
    assert list(run.outputs) == ["security", "coding"]


async def test_downstream_node_receives_the_upstream_payload(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)

    coding_prompt = provider.requests[1].user_prompt
    # The hand-off the whole design exists for: the coding agent is told what the
    # security agent found, as structured data.
    assert "Hardcoded API key" in coding_prompt
    assert "security-agent" in coding_prompt
    assert "config.py" in coding_prompt


async def test_first_node_receives_no_upstream(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)

    assert "Result from" not in provider.requests[0].user_prompt


async def test_each_node_is_persisted_as_completed(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    result = await seeded_session.execute(
        select(WorkflowNodeRecord).where(WorkflowNodeRecord.workflow_id == workflow.id)
    )
    nodes = {node.node_key: node for node in result.scalars()}

    assert nodes["security"].status == NodeStatus.COMPLETED
    assert nodes["security"].result_payload == SECURITY_FINDINGS
    assert nodes["coding"].status == NodeStatus.COMPLETED


async def test_workflow_cost_is_the_sum_of_its_nodes(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    run = await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    node_costs = sum(output.cost_usd for output in run.outputs.values())
    assert run.total_cost_usd == node_costs
    assert await repository.workflow_cost(workflow.id) == node_costs


async def test_final_result_comes_from_the_terminal_node(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    refreshed = await repository.get_workflow(workflow.id)
    assert refreshed.final_result["nodes"] == {"coding": CODE_CHANGES}
    assert refreshed.final_result["agents_run"] == ["security-agent", "coding-agent"]


async def test_three_node_chain_passes_data_along(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    provider.queue_json(DOCUMENT)
    repository = WorkflowRepository(seeded_session)
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix"),
            WorkflowNode(key="documentation", agent_id="documentation-agent", objective="Report"),
        ),
        edges=(
            WorkflowEdge(source="security", target="coding"),
            WorkflowEdge(source="coding", target="documentation"),
        ),
    )

    task = await repository.create_task(TaskRequest(request="Audit, fix, and report"))
    workflow = await repository.create_workflow(task.id, plan)
    run = await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)

    assert run.status is WorkflowStatus.COMPLETED
    # The documentation agent sees the code changes, not the security findings: it
    # depends only on the coding node, and hand-off follows dependencies.
    documentation_prompt = provider.requests[2].user_prompt
    assert "Moved the key" in documentation_prompt
    assert "Hardcoded API key" not in documentation_prompt


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


async def test_non_retryable_failure_stops_the_workflow(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    # Authentication is not retryable: a bad key will still be a bad key next time.
    provider.queue_failure(ErrorKind.AUTHENTICATION, "bad key")
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    run = await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    assert run.status is WorkflowStatus.FAILED
    # The downstream node must not run on missing input: a "fix" based on nothing is
    # worse than no fix.
    assert "coding" not in run.outputs
    assert len(provider.requests) == 1


async def test_failure_is_persisted_on_the_node_and_the_workflow(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.AUTHENTICATION, "bad key")
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    refreshed = await repository.get_workflow(workflow.id)
    nodes = {node.node_key: node for node in refreshed.nodes}

    assert refreshed.status == WorkflowStatus.FAILED
    assert refreshed.error is not None
    assert nodes["security"].status == NodeStatus.FAILED
    assert nodes["coding"].status == NodeStatus.WAITING

    task_record = await seeded_session.get(TaskRecord, task.id)
    assert task_record is not None
    assert task_record.status == TaskStatus.FAILED


async def test_invalid_output_also_stops_the_workflow(seeded_session: AsyncSession) -> None:
    provider = FakeProvider(default_response="not json at all")
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    run = await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)

    assert run.status is WorkflowStatus.FAILED
    assert run.outputs["security"].status is ExecutionStatus.INVALID_OUTPUT


async def test_budget_is_consumed_across_nodes(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)

    # Enough for the first node's estimate but not for a second: the workflow must stop
    # spending rather than quietly exceed the ceiling.
    run = await engine_for(seeded_session, provider).run(
        workflow.id, task.id, plan, budget_usd=0.02
    )
    await seeded_session.commit()

    assert run.outputs["security"].succeeded
    assert run.outputs["coding"].status is ExecutionStatus.BUDGET_EXCEEDED
    assert run.status is WorkflowStatus.FAILED


async def test_every_attempt_is_recorded(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_FINDINGS)
    provider.queue_json(CODE_CHANGES)
    repository = WorkflowRepository(seeded_session)
    plan = two_node_plan()

    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    result = await seeded_session.execute(select(ExecutionRecord))
    executions = list(result.scalars())

    assert len(executions) == 2
    assert all(execution.cost_usd > 0 for execution in executions)


# ---------------------------------------------------------------------------
# Orchestration service: request in, workflow out
# ---------------------------------------------------------------------------


async def test_security_request_activates_only_the_security_agent(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider(default_response=json.dumps(SECURITY_FINDINGS))

    result = await service_for(seeded_session, provider).submit(
        TaskRequest(request="Find security vulnerabilities in this repository")
    )
    await seeded_session.commit()

    agents_run = [node.agent_id for node in result.workflow.nodes]
    assert agents_run == ["security-agent"]
    assert result.run.status is WorkflowStatus.COMPLETED


async def test_broad_request_activates_several_agents(seeded_session: AsyncSession) -> None:
    provider = FakeProvider(
        default_response=json.dumps(
            {
                "findings": [],
                "steps": [{"description": "look", "capability": "research.web"}],
                "changes": [],
                "passed": True,
                "approved": True,
                "document": "report",
                "answer": "ok",
            }
        )
    )

    result = await service_for(seeded_session, provider).submit(
        TaskRequest(
            request=(
                "Analyse this repository for security vulnerabilities, fix what you "
                "find, write tests for the fixes, and document everything"
            )
        )
    )
    await seeded_session.commit()

    agents = {node.agent_id for node in result.workflow.nodes}
    assert {"security-agent", "coding-agent", "testing-agent", "documentation-agent"} <= agents
    assert "planning-agent" in agents


async def test_selection_record_is_persisted_with_the_workflow(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider(default_response=json.dumps(SECURITY_FINDINGS))

    result = await service_for(seeded_session, provider).submit(
        TaskRequest(request="Find security vulnerabilities")
    )
    await seeded_session.commit()

    selection = result.workflow.selection
    # "Only the necessary agents ran" has to be evidenced after the fact, not promised.
    assert selection["selected"] == ["security-agent"]
    assert "documentation-agent" in selection["excluded"]
    assert selection["reasoning"]


async def test_unservable_request_is_refused_and_recorded(
    session: AsyncSession,
) -> None:
    from app.agents.seed import upsert_agent
    from app.domain.enums import Capability
    from tests.test_registry import make_definition

    # A registry that can only write documents cannot audit security.
    await upsert_agent(session, make_definition("writer", {Capability.DOCUMENTATION}))
    await session.commit()
    provider = FakeProvider()

    try:
        await service_for(session, provider).submit(
            TaskRequest(request="Find security vulnerabilities in this repository")
        )
    except UnservableRequestError as exc:
        assert "security.vulnerability_analysis" in str(exc)
    else:
        raise AssertionError("expected the request to be refused")

    await session.commit()
    result = await session.execute(select(TaskRecord))
    task = result.scalar_one()
    # The task is kept as evidence of a coverage gap.
    assert task.status == TaskStatus.FAILED


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


async def test_submit_endpoint_runs_a_workflow(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json(SECURITY_FINDINGS)

    response = await db_client.post(
        "/api/v1/tasks", json={"request": "Find security vulnerabilities in this repository"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == WorkflowStatus.COMPLETED.value
    assert [node["agent_id"] for node in body["nodes"]] == ["security-agent"]
    assert body["nodes"][0]["result"] == SECURITY_FINDINGS
    assert body["total_cost_usd"] > 0


async def test_submit_endpoint_exposes_the_selection_reasoning(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json(SECURITY_FINDINGS)

    response = await db_client.post(
        "/api/v1/tasks", json={"request": "Find security vulnerabilities"}
    )

    selection = response.json()["selection"]
    assert selection["required_capabilities"]
    assert selection["excluded"]


async def test_plan_endpoint_previews_without_spending(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    response = await db_client.post(
        "/api/v1/tasks/plan", json={"request": "Find security vulnerabilities"}
    )

    assert response.status_code == 200
    body = response.json()
    assert [node["agent_id"] for node in body["nodes"]] == ["security-agent"]
    # The ceiling a user is agreeing to before committing: the sum of the selected
    # agents' cost limits.
    assert body["estimated_max_cost_usd"] == 0.75
    # No agent ran and no workflow exists: a preview that executed anything would
    # defeat its purpose.
    assert fake_provider.requests == []
    assert (await db_client.get("/api/v1/workflows")).json() == []


async def test_plan_endpoint_explains_exclusions(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/tasks/plan", json={"request": "Write a README for this project"}
    )

    body = response.json()
    assert "security-agent" in body["excluded_agents"]
    assert body["reasoning"]


async def test_submit_endpoint_rejects_an_empty_request(db_client: AsyncClient) -> None:
    response = await db_client.post("/api/v1/tasks", json={"request": ""})

    assert response.status_code == 422


async def test_workflow_from_a_task_can_be_fetched(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json(SECURITY_FINDINGS)
    created = await db_client.post(
        "/api/v1/tasks", json={"request": "Find security vulnerabilities"}
    )
    workflow_id = created.json()["id"]

    fetched = await db_client.get(f"/api/v1/workflows/{workflow_id}")

    assert fetched.status_code == 200
    assert fetched.json()["nodes"][0]["executions"][0]["attempt"] == 1


async def test_node_keys_are_stable_and_readable(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json(SECURITY_FINDINGS)

    response = await db_client.post(
        "/api/v1/tasks", json={"request": "Find security vulnerabilities"}
    )

    assert response.json()["nodes"][0]["key"] == "security"


def test_workflow_run_reports_completed_nodes() -> None:
    from app.workflows.engine import WorkflowRun

    run = WorkflowRun(workflow_id=uuid.uuid4(), status=WorkflowStatus.RUNNING)

    assert run.completed_nodes == ()
