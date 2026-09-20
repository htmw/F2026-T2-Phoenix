"""Task submission: the platform's primary entry point."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import (
    AbuseGuardDep,
    OperatorDep,
    OrchestrationServiceDep,
    ProviderRegistryDep,
    RepositoryDep,
    SessionDep,
    SettingsDep,
    WorkflowRunnerDep,
)
from app.schemas.api import WorkflowView
from app.schemas.workflow import TaskRequest
from app.services.generative_service import GenerativeOrchestrator
from app.services.orchestration_service import (
    UnknownModelOverrideError,
    UnservableRequestError,
)
from app.workflows.conditions import describe

router = APIRouter(prefix="/tasks", tags=["tasks"])


class PlanPreview(BaseModel):
    """What a request would do, before any money is spent."""

    required_capabilities: list[str]
    reasoning: str
    analysis_source: str
    nodes: list[dict[str, object]] = Field(default_factory=list)
    edges: list[dict[str, str | None]] = Field(default_factory=list)
    excluded_agents: dict[str, str] = Field(default_factory=dict)
    estimated_max_cost_usd: float = 0.0


@router.post("", response_model=WorkflowView, summary="Submit a task for orchestration")
async def submit_task(
    request: TaskRequest,
    service: OrchestrationServiceDep,
    runner: WorkflowRunnerDep,
    repository: RepositoryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
    wait: Annotated[
        bool,
        Query(description="Wait for the workflow to finish instead of returning immediately."),
    ] = True,
) -> WorkflowView:
    """Analyse the request, select agents, build a workflow, and run it.

    Requires operator identity (``X-Operator-Id`` or Bearer). The workflow is owned by
    that operator. With ``wait=false`` the response is the planned graph and execution
    continues in the background.

    Optional ``agent_ids`` forces an exact roster. ``routing_strategy`` is ``auto``
    (trait router + agent Fixed bindings), ``one`` (``shared_model`` for every agent),
    or ``mixed`` (``model_overrides`` per agent). Omit strategy fields to keep Auto.
    """
    try:
        if wait:
            result = await service.submit(request, owner_id=operator.id)
            return WorkflowView.from_record(result.workflow)

        prepared = await service.prepare(request, owner_id=operator.id)
        # Committed before the run is handed off: the background session must be able to
        # read the workflow it is about to execute.
        await repository.commit()
        runner.start(prepared)
        return WorkflowView.from_record(await repository.get_workflow(prepared.workflow_id))
    except UnknownModelOverrideError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except UnservableRequestError as exc:
        # 422, not 500: the request was understood and is simply outside what the
        # registered agents can do. The message names the uncovered capability.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/generative",
    response_model=WorkflowView,
    summary="Design a bespoke agent team for the request and run it (Level 3)",
)
async def submit_generative_task(
    request: TaskRequest,
    session: SessionDep,
    providers: ProviderRegistryDep,
    settings: SettingsDep,
    repository: RepositoryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> WorkflowView:
    """Design a team of specialist agents for this request, then run it to completion.

    Unlike ``POST /tasks``, no agent is selected from the registry: the team is generated
    per request, capped at ``generative_max_agents``, pinned to the cheapest model, and
    bounded by ``max_cost_usd`` (or the configured default). The run is synchronous
    because the generated agents live only in memory for this request.
    """
    service = GenerativeOrchestrator(session, providers, settings, repository)
    result = await service.submit(request, owner_id=operator.id)
    return WorkflowView.from_record(result.workflow)


@router.post(
    "/plan",
    response_model=PlanPreview,
    summary="Preview which agents a request would activate",
)
async def preview_plan(
    request: TaskRequest,
    service: OrchestrationServiceDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> PlanPreview:
    """Auth required so plan previews are attributable; no durable ownership yet."""
    _ = operator
    try:
        preview = await service.plan_only(request)
    except (UnservableRequestError, UnknownModelOverrideError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    analysis, plan = preview.analysis, preview.plan
    return PlanPreview(
        required_capabilities=sorted(capability.value for capability in analysis.required),
        reasoning=analysis.reasoning,
        analysis_source=analysis.source,
        nodes=[
            {
                "key": node.key,
                "agent_id": node.agent_id,
                "satisfies": [capability.value for capability in node.satisfies],
                "model": node.parameters.get("model"),
            }
            for node in plan.nodes
        ],
        edges=[
            {
                "source": edge.source,
                "target": edge.target,
                # A conditional edge means a downstream agent may not run at all, which
                # changes what the preview's cost ceiling actually means.
                "condition": describe(edge.condition, edge.source) if edge.condition else None,
            }
            for edge in plan.edges
        ],
        excluded_agents=plan.selection.excluded if plan.selection else {},
        estimated_max_cost_usd=preview.estimated_max_cost_usd,
    )
