"""Direct single-agent execution and workflow inspection."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.agents.registry import AgentNotFoundError
from app.api.dependencies import (
    AbuseGuardDep,
    AbuseStatusDep,
    OperatorDep,
    OrchestrationServiceDep,
    RepositoryDep,
    SingleAgentServiceDep,
    WorkflowRunnerDep,
)
from app.core.identity import OperatorIdentity
from app.domain.enums import WorkflowStatus
from app.schemas.api import AgentRunResponse, NodeDecision, OperatorLimitsView, WorkflowView
from app.schemas.workflow import TaskRequest
from app.services.orchestration_service import (
    NodeControlError,
    OrchestrationResult,
    WorkflowNotResumableError,
)
from app.services.workflow_repository import WorkflowNotFoundError, WorkflowRepository
from app.services.workflow_runner import WorkflowRunner

router = APIRouter(tags=["runs"])


@router.get(
    "/me/limits",
    response_model=OperatorLimitsView,
    summary="Current operator rate limit and budget status",
)
async def my_limits(operator: OperatorDep, limits: AbuseStatusDep) -> OperatorLimitsView:
    return OperatorLimitsView(
        operator_id=operator.id,
        rate_limit=limits.rate.limit,
        rate_remaining=limits.rate.remaining,
        rate_reset_at=limits.rate.reset_at,
        budget_cap_usd=limits.budget.cap_usd,
        budget_spent_usd=limits.budget.spent_usd,
        budget_window_hours=limits.budget.window_hours,
    )


@router.post(
    "/agents/{agent_id}/run",
    response_model=AgentRunResponse,
    summary="Run one agent directly",
)
async def run_agent(
    agent_id: str,
    request: TaskRequest,
    service: SingleAgentServiceDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> AgentRunResponse:
    """Execute a single named agent.

    Requires operator identity. Returns 200 even when the agent itself failed: the HTTP
    call succeeded, and the outcome — including a classified error — is in the body.
    """
    try:
        run = await service.run(agent_id, request, owner_id=operator.id)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"agent '{agent_id}' not found"
        ) from None

    return AgentRunResponse(workflow=WorkflowView.from_record(run.workflow), output=run.output)


@router.get("/workflows", response_model=list[WorkflowView], summary="List workflows")
async def list_workflows(
    repository: RepositoryDep,
    operator: OperatorDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[WorkflowView]:
    """List workflows owned by the calling operator."""
    records = await repository.list_workflows(limit=limit, owner_id=operator.id)
    # Execution detail is omitted from the list view: it is per-attempt data that only
    # matters once a specific workflow is opened.
    return [WorkflowView.from_record(record, include_executions=False) for record in records]


@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowView,
    summary="Get one workflow with execution detail",
)
async def get_workflow(
    workflow_id: uuid.UUID, repository: RepositoryDep, operator: OperatorDep
) -> WorkflowView:
    try:
        record = await repository.get_workflow(workflow_id, owner_id=operator.id)
    except WorkflowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"workflow '{workflow_id}' not found"
        ) from None
    return WorkflowView.from_record(record)


@router.get(
    "/workflows/{workflow_id}/thread",
    response_model=list[WorkflowView],
    summary="Get every turn in a workflow's conversation, oldest first",
)
async def get_thread(
    workflow_id: uuid.UUID, repository: RepositoryDep, operator: OperatorDep
) -> list[WorkflowView]:
    """Walk the ``parent_workflow_id`` chain so a client can render a whole conversation.

    Scoped to the calling operator; a turn owned by someone else simply ends the chain.
    """
    try:
        records = await repository.load_thread(workflow_id, owner_id=operator.id)
    except WorkflowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"workflow '{workflow_id}' not found"
        ) from None
    return [WorkflowView.from_record(record, include_executions=False) for record in records]


@router.post(
    "/workflows/{workflow_id}/cancel",
    response_model=WorkflowView,
    summary="Ask a running workflow to stop",
)
async def cancel_workflow(
    workflow_id: uuid.UUID,
    repository: RepositoryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> WorkflowView:
    """Request cancellation and return the workflow as it stands.

    Ownership is enforced. The response is not a promise that everything has stopped.
    """
    try:
        await repository.get_workflow(workflow_id, owner_id=operator.id)
        accepted = await repository.request_cancellation(workflow_id)
    except WorkflowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"workflow '{workflow_id}' not found"
        ) from None

    if not accepted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"workflow '{workflow_id}' has already finished",
        )
    await repository.commit()
    return WorkflowView.from_record(
        await repository.get_workflow(workflow_id, owner_id=operator.id)
    )


@router.post(
    "/workflows/{workflow_id}/resume",
    response_model=WorkflowView,
    summary="Continue a cancelled or interrupted workflow",
)
async def resume_workflow(
    workflow_id: uuid.UUID,
    service: OrchestrationServiceDep,
    runner: WorkflowRunnerDep,
    repository: RepositoryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
    wait: Annotated[
        bool, Query(description="Wait for the workflow to finish instead of returning immediately.")
    ] = True,
) -> WorkflowView:
    """Pick up where the workflow left off, without re-running finished nodes."""
    try:
        await repository.get_workflow(workflow_id, owner_id=operator.id)
        if wait:
            result = await service.resume(workflow_id)
            return WorkflowView.from_record(result.workflow)

        record = await repository.get_workflow(workflow_id, owner_id=operator.id)
        if record.status == WorkflowStatus.COMPLETED:
            raise WorkflowNotResumableError(f"workflow '{workflow_id}' has already completed")
        runner.start_resume(workflow_id)
        return WorkflowView.from_record(record)
    except WorkflowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"workflow '{workflow_id}' not found"
        ) from None
    except WorkflowNotResumableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/workflows/{workflow_id}/nodes/{node_key}/approve",
    response_model=WorkflowView,
    summary="Approve a node that is waiting on a human",
)
async def approve_node(
    workflow_id: uuid.UUID,
    node_key: str,
    service: OrchestrationServiceDep,
    runner: WorkflowRunnerDep,
    repository: RepositoryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
    decision: NodeDecision | None = None,
    wait: Annotated[
        bool, Query(description="Wait for the workflow to finish instead of returning immediately.")
    ] = True,
) -> WorkflowView:
    body = decision or NodeDecision()
    return await _control_node(
        workflow_id,
        runner,
        repository,
        operator,
        wait=wait,
        action=lambda continue_run: service.approve_node(
            workflow_id,
            node_key,
            decided_by=operator.id,
            reason=body.reason,
            continue_run=continue_run,
        ),
    )


@router.post(
    "/workflows/{workflow_id}/nodes/{node_key}/reject",
    response_model=WorkflowView,
    summary="Reject a node waiting on approval and skip its branch",
)
async def reject_node(
    workflow_id: uuid.UUID,
    node_key: str,
    service: OrchestrationServiceDep,
    runner: WorkflowRunnerDep,
    repository: RepositoryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
    decision: NodeDecision | None = None,
    wait: Annotated[
        bool, Query(description="Wait for the workflow to finish instead of returning immediately.")
    ] = True,
) -> WorkflowView:
    body = decision or NodeDecision()
    return await _control_node(
        workflow_id,
        runner,
        repository,
        operator,
        wait=wait,
        action=lambda continue_run: service.reject_node(
            workflow_id,
            node_key,
            decided_by=operator.id,
            reason=body.reason,
            continue_run=continue_run,
        ),
    )


@router.post(
    "/workflows/{workflow_id}/nodes/{node_key}/retry",
    response_model=WorkflowView,
    summary="Re-run a failed node and everything downstream of it",
)
async def retry_node(
    workflow_id: uuid.UUID,
    node_key: str,
    service: OrchestrationServiceDep,
    runner: WorkflowRunnerDep,
    repository: RepositoryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
    wait: Annotated[
        bool, Query(description="Wait for the workflow to finish instead of returning immediately.")
    ] = True,
) -> WorkflowView:
    return await _control_node(
        workflow_id,
        runner,
        repository,
        operator,
        wait=wait,
        action=lambda continue_run: service.retry_node(
            workflow_id, node_key, continue_run=continue_run
        ),
    )


@router.post(
    "/workflows/{workflow_id}/nodes/{node_key}/skip",
    response_model=WorkflowView,
    summary="Skip a node that has not completed",
)
async def skip_node(
    workflow_id: uuid.UUID,
    node_key: str,
    service: OrchestrationServiceDep,
    runner: WorkflowRunnerDep,
    repository: RepositoryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
    decision: NodeDecision | None = None,
    wait: Annotated[
        bool, Query(description="Wait for the workflow to finish instead of returning immediately.")
    ] = True,
) -> WorkflowView:
    body = decision or NodeDecision()
    return await _control_node(
        workflow_id,
        runner,
        repository,
        operator,
        wait=wait,
        action=lambda continue_run: service.skip_node(
            workflow_id, node_key, reason=body.reason, continue_run=continue_run
        ),
    )


async def _control_node(
    workflow_id: uuid.UUID,
    runner: WorkflowRunner,
    repository: WorkflowRepository,
    operator: OperatorIdentity,
    *,
    wait: bool,
    action: Callable[[bool], Awaitable[OrchestrationResult]],
) -> WorkflowView:
    """Apply a node control after verifying the caller owns the workflow."""
    try:
        await repository.get_workflow(workflow_id, owner_id=operator.id)
        result = await action(wait)
    except WorkflowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"workflow '{workflow_id}' not found"
        ) from None
    except NodeControlError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc
    except WorkflowNotResumableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if wait:
        return WorkflowView.from_record(result.workflow)

    runner.start_resume(workflow_id)
    return WorkflowView.from_record(
        await repository.get_workflow(workflow_id, owner_id=operator.id)
    )
