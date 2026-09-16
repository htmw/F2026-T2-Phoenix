"""Retries, feedback loops, cancellation, and resume.

These cover the parts of orchestration that only matter when something goes wrong, which
is most of the time: a transient provider error, a model that returns prose instead of
JSON, tests that fail and have to go back to the coding agent, and a user who changes
their mind mid-run.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.registry import DatabaseAgentRegistry, InMemoryAgentRegistry
from app.agents.seed import seed_agents
from app.domain.enums import (
    Capability,
    ErrorKind,
    ExecutionStatus,
    NodeStatus,
    TaskStatus,
    WorkflowStatus,
)
from app.models.workflow import TaskRecord
from app.orchestration.capability_analysis import CapabilityAnalysis, HeuristicCapabilityAnalyser
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import AgentSelector
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.agent import RetryPolicy
from app.schemas.workflow import (
    EdgeCondition,
    FeedbackRule,
    TaskRequest,
    WorkflowEdge,
    WorkflowNode,
    WorkflowPlan,
)
from app.services.agent_executor import AgentExecutor
from app.services.orchestration_service import OrchestrationService
from app.services.workflow_repository import WorkflowRepository
from app.workflows.engine import WorkflowEngine, WorkflowRun


def engine_for(
    session: AsyncSession, provider: FakeProvider, *, max_repair_cycles: int = 1
) -> WorkflowEngine:
    return WorkflowEngine(
        DatabaseAgentRegistry(session),
        AgentExecutor(ProviderRegistry([provider])),
        WorkflowRepository(session),
        max_repair_cycles=max_repair_cycles,
    )


async def seed_fast_retries(session: AsyncSession) -> None:
    """Re-seed the built-in agents with no backoff delay.

    Backoff is correct in production and pure latency in a test, so the policy is
    overridden here rather than shortened everywhere.
    """
    instant = RetryPolicy(max_attempts=3, initial_backoff_seconds=0.0)
    await seed_agents(
        session,
        tuple(agent.model_copy(update={"retry_policy": instant}) for agent in BUILTIN_AGENTS),
    )
    await session.commit()


async def run_plan(
    session: AsyncSession,
    provider: FakeProvider,
    plan: WorkflowPlan,
    *,
    max_repair_cycles: int = 1,
    request: str = "Fix and test this repository",
) -> tuple[WorkflowRun, WorkflowRepository, uuid.UUID]:
    repository = WorkflowRepository(session)
    task = await repository.create_task(TaskRequest(request=request))
    workflow = await repository.create_workflow(task.id, plan)
    run = await engine_for(session, provider, max_repair_cycles=max_repair_cycles).run(
        workflow.id, task.id, plan
    )
    return run, repository, workflow.id


def single_node_plan(agent_id: str = "security-agent") -> WorkflowPlan:
    return WorkflowPlan(
        nodes=(WorkflowNode(key="security", agent_id=agent_id, objective="Audit the repo"),)
    )


def code_then_test_plan() -> WorkflowPlan:
    """coding → testing, where failing tests send work back to coding."""
    return WorkflowPlan(
        nodes=(
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Write the feature"),
            WorkflowNode(
                key="testing",
                agent_id="testing-agent",
                objective="Test the change",
                feedback=FeedbackRule(
                    target="coding",
                    condition=EdgeCondition(path="passed", operator="is_false"),
                    detail_path="failures",
                    message="The tests failed. Revise the change.",
                ),
            ),
        ),
        edges=(WorkflowEdge(source="coding", target="testing"),),
    )


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------


async def test_transient_failure_is_retried_and_can_succeed(
    seeded_session: AsyncSession,
) -> None:
    await seed_fast_retries(seeded_session)
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.PROVIDER_UNAVAILABLE, "provider down")
    provider.queue_json({"findings": [{"severity": "low", "issue": "Weak cipher"}]})

    run, _, _ = await run_plan(seeded_session, provider, single_node_plan())

    # One bad response must not cost the whole workflow.
    assert run.status is WorkflowStatus.COMPLETED
    assert run.outputs["security"].succeeded
    assert len(provider.requests) == 2


async def test_every_attempt_is_recorded(seeded_session: AsyncSession) -> None:
    await seed_fast_retries(seeded_session)
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.TIMEOUT, "took too long")
    provider.queue_json({"findings": []})

    _, repository, workflow_id = await run_plan(seeded_session, provider, single_node_plan())
    await seeded_session.commit()

    workflow = await repository.get_workflow(workflow_id)
    node = next(node for node in workflow.nodes if node.node_key == "security")
    attempts = sorted(node.executions, key=lambda execution: execution.attempt)

    # The failed attempt is history, not noise: it is what explains the latency and the
    # cost of a run that looks like it only did one thing.
    assert [execution.attempt for execution in attempts] == [1, 2]
    assert attempts[0].status == ExecutionStatus.FAILED
    assert attempts[0].error_kind == ErrorKind.TIMEOUT.value
    assert attempts[1].status == ExecutionStatus.SUCCEEDED
    assert node.attempts == 2
    assert node.status == NodeStatus.COMPLETED


async def test_non_retryable_error_is_not_retried(seeded_session: AsyncSession) -> None:
    await seed_fast_retries(seeded_session)
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.AUTHENTICATION, "bad key")
    provider.queue_json({"findings": []})

    run, _, _ = await run_plan(seeded_session, provider, single_node_plan())

    # Retrying a bad API key burns latency and money for a guaranteed second failure.
    assert run.status is WorkflowStatus.FAILED
    assert len(provider.requests) == 1


async def test_retries_are_exhausted_then_the_workflow_fails(
    seeded_session: AsyncSession,
) -> None:
    await seed_fast_retries(seeded_session)
    provider = FakeProvider()
    for _ in range(3):
        provider.queue_failure(ErrorKind.PROVIDER_UNAVAILABLE, "still down")

    run, repository, workflow_id = await run_plan(seeded_session, provider, single_node_plan())
    await seeded_session.commit()

    assert run.status is WorkflowStatus.FAILED
    assert len(provider.requests) == 3  # max_attempts, not more

    workflow = await repository.get_workflow(workflow_id)
    node = next(node for node in workflow.nodes if node.node_key == "security")
    assert node.status == NodeStatus.FAILED
    assert node.attempts == 3


async def test_a_schema_violation_is_retried_with_the_reason(
    seeded_session: AsyncSession,
) -> None:
    await seed_fast_retries(seeded_session)
    provider = FakeProvider()
    provider.queue_response("Here you go: the code looks fine to me!")
    provider.queue_json({"findings": []})

    run, _, _ = await run_plan(seeded_session, provider, single_node_plan())

    assert run.status is WorkflowStatus.COMPLETED
    # Repeating an identical prompt tends to reproduce the same malformed answer, so the
    # retry is told what was wrong with the last one.
    second_prompt = provider.requests[1].user_prompt
    assert "rejected" in second_prompt.lower()


async def test_backoff_is_taken_from_the_agents_own_policy(
    seeded_session: AsyncSession,
) -> None:
    policy = RetryPolicy(max_attempts=3, initial_backoff_seconds=2.0, backoff_multiplier=3.0)

    # Attempt 1 is the initial try, so it waits for nothing.
    assert policy.backoff_for_attempt(1) == 0.0
    assert policy.backoff_for_attempt(2) == 2.0
    assert policy.backoff_for_attempt(3) == 6.0
    assert policy.backoff_for_attempt(9) == policy.max_backoff_seconds


# ---------------------------------------------------------------------------
# Feedback routing
# ---------------------------------------------------------------------------


async def test_failing_tests_send_work_back_to_the_coding_agent(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json({"changes": [{"file": "app.py", "action": "modify"}]})
    provider.queue_json(
        {
            "passed": False,
            "failures": [{"test": "test_login", "message": "test_login asserts 200, got 500"}],
        }
    )
    provider.queue_json({"changes": [{"file": "app.py", "action": "modify"}]})
    provider.queue_json({"passed": True, "tests": [{"name": "test_login"}]})

    run, _, _ = await run_plan(seeded_session, provider, code_then_test_plan())

    assert run.status is WorkflowStatus.COMPLETED
    assert run.repairs == {"coding": 1}
    # Four calls: code, test, revise, test again.
    assert len(provider.requests) == 4
    assert run.outputs["testing"].payload["passed"] is True


async def test_the_revision_is_told_what_failed(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json({"changes": [{"file": "app.py", "action": "modify"}]})
    provider.queue_json(
        {
            "passed": False,
            "failures": [{"test": "test_login", "message": "test_login asserts 200, got 500"}],
        }
    )
    provider.queue_json({"changes": [{"file": "app.py", "action": "modify"}]})
    provider.queue_json({"passed": True})

    await run_plan(seeded_session, provider, code_then_test_plan())

    revision_prompt = provider.requests[2].user_prompt
    # The detail comes from the testing agent's own payload, not from prose invented by
    # the engine.
    assert "test_login asserts 200, got 500" in revision_prompt


async def test_a_repair_reruns_everything_downstream(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json({"changes": []})
    provider.queue_json({"passed": False, "failures": [{"test": "suite", "message": "broken"}]})
    provider.queue_json({"changes": []})
    provider.queue_json({"passed": True})

    _, repository, workflow_id = await run_plan(seeded_session, provider, code_then_test_plan())
    await seeded_session.commit()

    workflow = await repository.get_workflow(workflow_id)
    nodes = {node.node_key: node for node in workflow.nodes}

    # Both nodes ran twice, and attempt numbers continue rather than restarting: the
    # history should read as one sequence of tries.
    assert nodes["coding"].attempts == 2
    assert nodes["testing"].attempts == 2
    assert [
        execution.attempt
        for execution in sorted(nodes["coding"].executions, key=lambda e: e.attempt)
    ] == [1, 2]
    assert nodes["coding"].status == NodeStatus.COMPLETED
    assert nodes["testing"].status == NodeStatus.COMPLETED


async def test_the_repair_loop_is_bounded(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    still_broken = {
        "passed": False,
        "failures": [{"test": "suite", "message": "still broken"}],
    }
    provider.queue_json({"changes": []})
    provider.queue_json(still_broken)
    provider.queue_json({"changes": []})
    provider.queue_json(still_broken)

    run, _, _ = await run_plan(seeded_session, provider, code_then_test_plan(), max_repair_cycles=1)

    # A coding agent and a testing agent can disagree forever, and each round costs
    # money. The verdict stands and the workflow completes with it recorded.
    assert run.repairs == {"coding": 1}
    assert run.status is WorkflowStatus.COMPLETED
    assert run.outputs["testing"].payload["passed"] is False


async def test_zero_repair_cycles_disables_the_loop(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json({"changes": []})
    provider.queue_json({"passed": False, "failures": [{"test": "suite", "message": "broken"}]})

    run, _, _ = await run_plan(seeded_session, provider, code_then_test_plan(), max_repair_cycles=0)

    assert run.repairs == {}
    assert len(provider.requests) == 2


async def test_passing_tests_do_not_trigger_a_repair(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json({"changes": []})
    provider.queue_json({"passed": True})

    run, _, _ = await run_plan(seeded_session, provider, code_then_test_plan())

    assert run.repairs == {}
    assert len(provider.requests) == 2


async def test_planner_wires_the_testing_verdict_back_to_coding() -> None:
    registry = InMemoryAgentRegistry(list(BUILTIN_AGENTS))
    required = frozenset({Capability.CODE_MODIFICATION, Capability.TEST_GENERATION})
    selection = await AgentSelector(registry).select(required)
    analysis = CapabilityAnalysis(required=required, reasoning="test", source="test")

    plan = WorkflowPlanner().plan("Fix and test", analysis, selection)

    rule = plan.node("testing").feedback
    assert rule is not None
    assert rule.target == "coding"
    assert rule.condition.path == "passed"
    assert plan.node("coding").feedback is None


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


async def test_cancellation_stops_scheduling_at_the_batch_boundary(
    seeded_session: AsyncSession,
) -> None:
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix"),
        ),
        edges=(WorkflowEdge(source="security", target="coding"),),
    )
    repository = WorkflowRepository(seeded_session)
    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await repository.request_cancellation(workflow.id)
    await seeded_session.commit()

    provider = FakeProvider()
    run = await engine_for(seeded_session, provider).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    assert run.status is WorkflowStatus.CANCELLED
    assert provider.requests == []

    refreshed = await repository.get_workflow(workflow.id)
    assert refreshed.status == WorkflowStatus.CANCELLED
    assert all(node.status == NodeStatus.CANCELLED for node in refreshed.nodes)

    task_record = await seeded_session.get(TaskRecord, task.id)
    assert task_record is not None
    assert task_record.status == TaskStatus.CANCELLED


async def test_cancelling_a_finished_workflow_is_refused(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": []})
    _, repository, workflow_id = await run_plan(seeded_session, provider, single_node_plan())

    # Nothing to stop, and pretending otherwise would misreport a completed run.
    assert await repository.request_cancellation(workflow_id) is False


async def test_completed_work_survives_cancellation(seeded_session: AsyncSession) -> None:
    """A mid-run cancellation keeps what was already paid for."""
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix"),
        ),
        edges=(WorkflowEdge(source="security", target="coding"),),
    )
    repository = WorkflowRepository(seeded_session)
    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await seeded_session.commit()

    provider = FakeProvider()
    provider.queue_json({"findings": [{"severity": "high", "issue": "SQL injection"}]})

    # Cancel as soon as the first node's result has been written.
    original = repository.record_execution

    async def cancel_after_first(*args: object, **kwargs: object) -> object:
        record = await original(*args, **kwargs)  # type: ignore[arg-type]
        await repository.request_cancellation(workflow.id)
        return record

    repository.record_execution = cancel_after_first  # type: ignore[assignment,method-assign]
    run = await WorkflowEngine(
        DatabaseAgentRegistry(seeded_session),
        AgentExecutor(ProviderRegistry([provider])),
        repository,
    ).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    assert run.status is WorkflowStatus.CANCELLED
    assert "security" in run.completed_nodes

    refreshed = await repository.get_workflow(workflow.id)
    nodes = {node.node_key: node for node in refreshed.nodes}
    assert nodes["security"].status == NodeStatus.COMPLETED
    assert nodes["security"].result_payload["findings"]
    assert nodes["coding"].status == NodeStatus.CANCELLED


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def service_for(session: AsyncSession, provider: FakeProvider) -> OrchestrationService:
    registry = DatabaseAgentRegistry(session)
    return OrchestrationService(
        HeuristicCapabilityAnalyser(),
        AgentSelector(registry),
        WorkflowPlanner(),
        engine_for(session, provider),
        WorkflowRepository(session),
    )


async def test_resume_does_not_rerun_completed_nodes(seeded_session: AsyncSession) -> None:
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix"),
        ),
        edges=(WorkflowEdge(source="security", target="coding"),),
    )
    repository = WorkflowRepository(seeded_session)
    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await seeded_session.commit()

    # First pass: run the audit, then cancel before the fix.
    provider = FakeProvider()
    provider.queue_json({"findings": [{"severity": "high", "issue": "SQL injection"}]})
    original = repository.record_execution

    async def cancel_after_first(*args: object, **kwargs: object) -> object:
        record = await original(*args, **kwargs)  # type: ignore[arg-type]
        await repository.request_cancellation(workflow.id)
        return record

    repository.record_execution = cancel_after_first  # type: ignore[assignment,method-assign]
    await WorkflowEngine(
        DatabaseAgentRegistry(seeded_session),
        AgentExecutor(ProviderRegistry([provider])),
        repository,
    ).run(workflow.id, task.id, plan)
    await seeded_session.commit()

    # Second pass: resume with a fresh provider that only answers the remaining node.
    resumed_provider = FakeProvider()
    resumed_provider.queue_json({"changes": [{"file": "db.py", "action": "modify"}]})
    result = await service_for(seeded_session, resumed_provider).resume(workflow.id)
    await seeded_session.commit()

    assert result.run.status is WorkflowStatus.COMPLETED
    # Exactly one call: the audit was not paid for twice.
    assert len(resumed_provider.requests) == 1
    assert "coding" in result.run.outputs


async def test_resume_hands_the_earlier_result_to_the_remaining_node(
    seeded_session: AsyncSession,
) -> None:
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(key="coding", agent_id="coding-agent", objective="Fix"),
        ),
        edges=(WorkflowEdge(source="security", target="coding"),),
    )
    repository = WorkflowRepository(seeded_session)
    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)

    # Simulate a process that died after the first node: the result is committed, the
    # workflow is still marked running.
    provider = FakeProvider()
    provider.queue_json({"findings": [{"severity": "high", "issue": "SQL injection in db.py"}]})
    await repository.start_workflow(workflow.id)
    engine = engine_for(seeded_session, provider)
    partial_plan = WorkflowPlan(nodes=(plan.node("security"),))
    await engine.run(workflow.id, task.id, partial_plan)
    await repository.finish_workflow(workflow.id, WorkflowStatus.RUNNING)
    await seeded_session.commit()

    resumed_provider = FakeProvider()
    resumed_provider.queue_json({"changes": [{"file": "db.py", "action": "modify"}]})
    await service_for(seeded_session, resumed_provider).resume(workflow.id)

    # The hand-off has to come from the database, or the resumed node works blind.
    assert "SQL injection in db.py" in resumed_provider.requests[0].user_prompt


async def test_resume_rebuilds_the_graph_from_the_database(
    seeded_session: AsyncSession,
) -> None:
    plan = WorkflowPlan(
        nodes=(
            WorkflowNode(key="security", agent_id="security-agent", objective="Audit"),
            WorkflowNode(
                key="coding",
                agent_id="coding-agent",
                objective="Fix",
                feedback=FeedbackRule(
                    target="security",
                    condition=EdgeCondition(path="changes", operator="empty"),
                ),
            ),
        ),
        edges=(
            WorkflowEdge(
                source="security",
                target="coding",
                condition=EdgeCondition(path="findings", operator="non_empty"),
            ),
        ),
    )
    repository = WorkflowRepository(seeded_session)
    task = await repository.create_task(TaskRequest(request="Audit and fix"))
    workflow = await repository.create_workflow(task.id, plan)
    await seeded_session.commit()

    loaded = await repository.load_plan(workflow.id)

    # Re-planning on resume could silently execute a different shape than the one the
    # user was shown, so the graph is reloaded rather than recomputed.
    assert [node.key for node in loaded.nodes] == ["security", "coding"]
    assert loaded.edges[0].condition is not None
    assert loaded.edges[0].condition.operator == "non_empty"
    feedback = loaded.node("coding").feedback
    assert feedback is not None
    assert feedback.target == "security"


async def test_resuming_a_completed_workflow_is_refused(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": []})
    _, _, workflow_id = await run_plan(seeded_session, provider, single_node_plan())
    await seeded_session.commit()

    service = service_for(seeded_session, FakeProvider())
    try:
        await service.resume(workflow_id)
    except Exception as exc:  # WorkflowNotResumableError
        assert "already completed" in str(exc)
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("resuming a completed workflow should be refused")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


async def test_cancel_endpoint_reports_the_request(
    db_client: AsyncClient, fake_provider: FakeProvider, session_factory: object
) -> None:
    fake_provider.queue_json({"findings": []})
    submitted = await db_client.post(
        "/api/v1/tasks", json={"request": "Audit this repository for vulnerabilities"}
    )
    workflow_id = submitted.json()["id"]

    # The workflow has already finished, so cancelling it is a conflict rather than a
    # silent no-op that would misreport a completed run.
    response = await db_client.post(f"/api/v1/workflows/{workflow_id}/cancel")
    assert response.status_code == 409


async def test_cancel_endpoint_404s_for_an_unknown_workflow(db_client: AsyncClient) -> None:
    response = await db_client.post(f"/api/v1/workflows/{uuid.uuid4()}/cancel")
    assert response.status_code == 404


async def test_async_submission_returns_the_graph_before_it_runs(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json({"findings": []})

    response = await db_client.post(
        "/api/v1/tasks?wait=false",
        json={"request": "Audit this repository for vulnerabilities"},
    )

    assert response.status_code == 200
    body = response.json()
    # A user staring at an empty screen cannot tell "thinking" from "broken", so the
    # graph is returned immediately and the run continues in the background.
    assert body["status"] in {WorkflowStatus.PENDING.value, WorkflowStatus.RUNNING.value}
    assert [node["key"] for node in body["nodes"]] == ["security"]


async def test_background_run_reaches_completion(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json({"findings": []})

    submitted = await db_client.post(
        "/api/v1/tasks?wait=false",
        json={"request": "Audit this repository for vulnerabilities"},
    )
    workflow_id = submitted.json()["id"]

    runner = db_client._transport.app.state.workflow_runner  # type: ignore[attr-defined]
    assert await runner.wait_for(uuid.UUID(workflow_id), seconds=30)

    polled = await db_client.get(f"/api/v1/workflows/{workflow_id}")
    assert polled.json()["status"] == WorkflowStatus.COMPLETED.value


async def test_resume_endpoint_409s_for_a_completed_workflow(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json({"findings": []})
    submitted = await db_client.post(
        "/api/v1/tasks", json={"request": "Audit this repository for vulnerabilities"}
    )
    workflow_id = submitted.json()["id"]

    response = await db_client.post(f"/api/v1/workflows/{workflow_id}/resume")
    assert response.status_code == 409
