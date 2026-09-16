"""End-to-end single-agent execution: persistence, cost accounting, and the HTTP path.

These run against real PostgreSQL and a scripted provider, so they verify the whole
path a task takes — task row, workflow, node, execution attempt, stored result — without
a network call.
"""

from __future__ import annotations

import json

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import DatabaseAgentRegistry
from app.domain.enums import ErrorKind, ExecutionStatus, NodeStatus, TaskStatus, WorkflowStatus
from app.models.workflow import AgentResultRecord, ExecutionRecord, TaskRecord, WorkflowRecord
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.workflow import TaskRequest
from app.services.agent_executor import AgentExecutor
from app.services.single_agent_service import SingleAgentService
from app.services.workflow_repository import WorkflowRepository

SECURITY_PAYLOAD: dict[str, object] = {
    "findings": [{"severity": "high", "issue": "Hardcoded credential", "file": "app.py"}],
    "summary": "One high-severity issue.",
}


def service_for(session: AsyncSession, provider: FakeProvider) -> SingleAgentService:
    return SingleAgentService(
        DatabaseAgentRegistry(session),
        AgentExecutor(ProviderRegistry([provider])),
        WorkflowRepository(session),
    )


async def test_successful_run_persists_task_workflow_and_result(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_PAYLOAD)

    run = await service_for(seeded_session, provider).run(
        "security-agent", TaskRequest(request="Audit this repository for vulnerabilities")
    )
    await seeded_session.commit()

    assert run.output.status is ExecutionStatus.SUCCEEDED
    assert run.workflow.status == WorkflowStatus.COMPLETED
    assert run.workflow.final_result == SECURITY_PAYLOAD

    task = await seeded_session.get(TaskRecord, run.workflow.task_id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED


async def test_successful_run_records_the_node_result(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_PAYLOAD)

    run = await service_for(seeded_session, provider).run(
        "security-agent", TaskRequest(request="Audit this repository")
    )
    await seeded_session.commit()

    node = run.workflow.nodes[0]
    assert node.node_key == "main"
    assert node.status == NodeStatus.COMPLETED
    assert node.result_payload == SECURITY_PAYLOAD
    assert node.attempts == 1


async def test_run_records_an_execution_with_tokens_cost_and_timing(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_PAYLOAD)

    run = await service_for(seeded_session, provider).run(
        "security-agent", TaskRequest(request="Audit this repository")
    )
    await seeded_session.commit()

    result = await seeded_session.execute(
        select(ExecutionRecord).where(ExecutionRecord.node_id == run.workflow.nodes[0].id)
    )
    execution = result.scalar_one()

    # Without this record there is no way to answer "what did this task cost".
    assert execution.attempt == 1
    assert execution.status == ExecutionStatus.SUCCEEDED
    assert execution.input_tokens > 0
    assert execution.output_tokens > 0
    assert execution.cost_usd > 0
    assert execution.provider_id == "fake"
    assert execution.started_at is not None
    assert execution.completed_at is not None


async def test_workflow_cost_accumulates_the_execution_cost(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_PAYLOAD)

    run = await service_for(seeded_session, provider).run(
        "security-agent", TaskRequest(request="Audit this repository")
    )
    await seeded_session.commit()

    refreshed = await seeded_session.get(WorkflowRecord, run.workflow.id)
    assert refreshed is not None
    assert refreshed.total_cost_usd == run.output.cost_usd
    assert refreshed.total_cost_usd > 0


async def test_invalid_output_fails_the_workflow_and_keeps_the_raw_text(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider(default_response="I cannot comply.")

    run = await service_for(seeded_session, provider).run(
        "security-agent", TaskRequest(request="Audit this repository")
    )
    await seeded_session.commit()

    assert run.output.status is ExecutionStatus.INVALID_OUTPUT
    assert run.workflow.status == WorkflowStatus.FAILED
    assert run.workflow.nodes[0].status == NodeStatus.FAILED

    result = await seeded_session.execute(select(AgentResultRecord))
    stored = result.scalar_one()
    assert stored.schema_valid is False
    assert stored.raw_output == "I cannot comply."
    assert stored.validation_error is not None


async def test_successful_run_does_not_store_raw_completion_text(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_PAYLOAD)

    await service_for(seeded_session, provider).run(
        "security-agent", TaskRequest(request="Audit this repository")
    )
    await seeded_session.commit()

    result = await seeded_session.execute(select(AgentResultRecord))
    stored = result.scalar_one()
    # Raw text is kept only for failures: storing every completion is a privacy and
    # storage cost with no debugging benefit.
    assert stored.raw_output is None
    assert stored.schema_valid is True


async def test_provider_failure_is_recorded_with_its_classification(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.RATE_LIMITED, "slow down")

    run = await service_for(seeded_session, provider).run(
        "security-agent", TaskRequest(request="Audit this repository")
    )
    await seeded_session.commit()

    result = await seeded_session.execute(select(ExecutionRecord))
    execution = result.scalar_one()

    assert execution.status == ExecutionStatus.FAILED
    assert execution.error_kind == ErrorKind.RATE_LIMITED.value
    assert run.workflow.status == WorkflowStatus.FAILED
    assert run.workflow.error is not None


async def test_budget_refusal_is_recorded_without_spend(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_PAYLOAD)

    run = await service_for(seeded_session, provider).run(
        "security-agent",
        # A ceiling far below any real call, so the pre-flight check must refuse.
        TaskRequest(request="Audit this repository", max_cost_usd=0.000001),
    )
    await seeded_session.commit()

    assert run.output.status is ExecutionStatus.BUDGET_EXCEEDED
    assert run.workflow.total_cost_usd == 0.0
    assert provider.requests == []


async def test_objective_reaches_the_provider_prompt(seeded_session: AsyncSession) -> None:
    provider = FakeProvider()
    provider.queue_json(SECURITY_PAYLOAD)

    await service_for(seeded_session, provider).run(
        "security-agent", TaskRequest(request="Audit payments-service for SQL injection")
    )

    assert "payments-service" in provider.requests[0].user_prompt


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


async def test_run_endpoint_returns_the_workflow_and_output(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json(SECURITY_PAYLOAD)

    response = await db_client.post(
        "/api/v1/agents/security-agent/run",
        json={"request": "Audit this repository for vulnerabilities"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output"]["status"] == ExecutionStatus.SUCCEEDED.value
    assert body["output"]["payload"] == SECURITY_PAYLOAD
    assert body["workflow"]["status"] == WorkflowStatus.COMPLETED.value
    assert body["workflow"]["nodes"][0]["agent_id"] == "security-agent"
    assert body["workflow"]["total_cost_usd"] > 0


async def test_run_endpoint_reports_agent_failure_as_a_200_with_an_error(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_failure(ErrorKind.PROVIDER_UNAVAILABLE, "upstream down")

    response = await db_client.post(
        "/api/v1/agents/security-agent/run", json={"request": "Audit this repository"}
    )

    # The HTTP call succeeded; the agent did not. Conflating the two would make the
    # failure indistinguishable from a platform bug.
    assert response.status_code == 200
    body = response.json()
    assert body["output"]["status"] == ExecutionStatus.FAILED.value
    assert body["output"]["error"]["kind"] == ErrorKind.PROVIDER_UNAVAILABLE.value
    assert body["output"]["error"]["retryable"] is True


async def test_run_endpoint_404s_for_an_unknown_agent(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/agents/imaginary-agent/run", json={"request": "Do something"}
    )

    assert response.status_code == 404


async def test_run_endpoint_rejects_an_empty_request(db_client: AsyncClient) -> None:
    response = await db_client.post("/api/v1/agents/security-agent/run", json={"request": ""})

    assert response.status_code == 422


async def test_workflow_can_be_fetched_after_a_run(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json(SECURITY_PAYLOAD)

    created = await db_client.post(
        "/api/v1/agents/security-agent/run", json={"request": "Audit this repository"}
    )
    workflow_id = created.json()["workflow"]["id"]

    fetched = await db_client.get(f"/api/v1/workflows/{workflow_id}")

    assert fetched.status_code == 200
    body = fetched.json()
    assert body["id"] == workflow_id
    # Attempt-level detail is what makes a run auditable after the fact.
    assert body["nodes"][0]["executions"][0]["cost_usd"] > 0
    assert body["nodes"][0]["executions"][0]["provider"] == "fake"


async def test_workflow_list_returns_recent_workflows(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    for _ in range(3):
        fake_provider.queue_json(SECURITY_PAYLOAD)
        await db_client.post(
            "/api/v1/agents/security-agent/run", json={"request": "Audit this repository"}
        )

    response = await db_client.get("/api/v1/workflows")

    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_unknown_workflow_returns_404(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/workflows/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_provider_endpoint_lists_models_without_credentials(
    db_client: AsyncClient,
) -> None:
    response = await db_client.get("/api/v1/providers")

    assert response.status_code == 200
    body = response.json()
    assert body
    serialised = json.dumps(body)
    # Any string that looks like a credential here would be a leak.
    assert "sk-" not in serialised
    assert "api_key" not in serialised
