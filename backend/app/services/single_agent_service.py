"""Running one agent against one request, persisted end to end.

This is the smallest complete path through the system: task → single-node workflow →
execution → validated result. It exists before the orchestrator on purpose, so the
expensive parts (provider call, validation, persistence, cost accounting) are proven in
isolation, and so Sprint 3 can add graph construction without also debugging execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.registry import AgentRegistry
from app.core.logging import get_logger
from app.domain.enums import (
    AgentRuntimeStatus,
    DecisionKind,
    NodeStatus,
    TaskStatus,
    WorkflowStatus,
)
from app.messaging.store import DecisionService, PresenceService
from app.models.workflow import WorkflowRecord
from app.schemas.execution import AgentInput, AgentOutput
from app.schemas.memory import DecisionCreate
from app.schemas.workflow import TaskRequest, WorkflowNode, WorkflowPlan
from app.services.agent_executor import AgentExecutor, ExecutionContext
from app.services.workflow_repository import WorkflowRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SingleAgentRun:
    workflow: WorkflowRecord
    output: AgentOutput


class SingleAgentService:
    def __init__(
        self,
        registry: AgentRegistry,
        executor: AgentExecutor,
        repository: WorkflowRepository,
        presence: PresenceService | None = None,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._repository = repository
        self._presence = presence

    async def run(
        self, agent_id: str, request: TaskRequest, *, owner_id: str = "operator"
    ) -> SingleAgentRun:
        agent = await self._registry.get(agent_id)

        task = await self._repository.create_task(request, owner_id=owner_id)
        plan = WorkflowPlan(
            nodes=(
                WorkflowNode(
                    key="main",
                    agent_id=agent.id,
                    objective=request.request,
                    parameters=request.parameters,
                    satisfies=tuple(sorted(agent.capabilities)),
                ),
            )
        )
        workflow = await self._repository.create_workflow(task.id, plan, owner_id=owner_id)

        await self._repository.start_workflow(workflow.id)
        await self._repository.set_task_status(task.id, TaskStatus.RUNNING)
        await self._repository.set_node_status(workflow.id, "main", NodeStatus.RUNNING)
        if self._presence is not None:
            await self._presence.set(
                agent.id,
                AgentRuntimeStatus.WORKING,
                current_task=request.request,
                detail="running main",
            )

        output = await self._executor.execute(
            agent,
            AgentInput(
                task_id=task.id,
                node_key="main",
                agent_id=agent.id,
                objective=request.request,
                parameters=request.parameters,
            ),
            ExecutionContext(remaining_budget_usd=request.max_cost_usd),
        )

        raw_output = None
        if output.error is not None:
            raw = output.error.details.get("raw_output")
            raw_output = raw if isinstance(raw, str) else None

        await self._repository.record_execution(workflow.id, output, raw_output=raw_output)

        if output.routing_reason or output.provider:
            model_label = (
                f"{output.provider}:{output.model}"
                if output.provider and output.model
                else output.model or output.provider or "unknown"
            )
            await DecisionService(self._repository._session).record(
                DecisionCreate(
                    kind=DecisionKind.ROUTING,
                    actor_id="executor",
                    agent_id=agent.id,
                    workflow_id=workflow.id,
                    node_key="main",
                    title=f"Routed main → {model_label}",
                    summary=output.routing_reason,
                    payload={
                        "provider": output.provider,
                        "model": output.model,
                        "reason": output.routing_reason,
                        "alternatives": list(output.routing_alternatives),
                        "attempt": output.attempt,
                        "status": output.status.value,
                        "succeeded": output.succeeded,
                    },
                    tags=("routing", "execution", output.status.value),
                    importance=0.75,
                )
            )

        if output.succeeded:
            await self._repository.finish_workflow(
                workflow.id, WorkflowStatus.COMPLETED, final_result=output.payload
            )
            await self._repository.set_task_status(task.id, TaskStatus.COMPLETED)
            if self._presence is not None:
                await self._presence.set(
                    agent.id, AgentRuntimeStatus.IDLE, detail="completed"
                )
        else:
            # A single-node workflow has nowhere to recover to, so a failed attempt ends
            # the workflow. Retries and alternative routing arrive with the engine.
            await self._repository.mark_node_failed(workflow.id, "main")
            await self._repository.finish_workflow(
                workflow.id,
                WorkflowStatus.FAILED,
                error=output.error.message if output.error else "agent failed",
            )
            await self._repository.set_task_status(task.id, TaskStatus.FAILED)
            if self._presence is not None:
                await self._presence.set(
                    agent.id,
                    AgentRuntimeStatus.FAILED,
                    detail=output.error.message if output.error else "failed",
                )

        logger.info(
            "single_agent_run_finished",
            workflow_id=str(workflow.id),
            agent_id=agent.id,
            status=output.status.value,
            cost_usd=round(output.cost_usd, 6),
        )

        refreshed = await self._repository.get_workflow(workflow.id)
        return SingleAgentRun(workflow=refreshed, output=output)
