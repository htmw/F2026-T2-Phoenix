"""The use case: a plain-English request becomes a planned, executed workflow.

This is the seam between HTTP and the engine. It owns the sequence — analyse, select,
plan, persist, execute — and nothing else; each step is a collaborator that can be
tested and replaced independently.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.logging import get_logger
from app.domain.enums import DecisionKind, NodeStatus, RoutingStrategy, TaskStatus, WorkflowStatus
from app.messaging.store import DecisionService
from app.models.workflow import WorkflowNodeRecord, WorkflowRecord
from app.orchestration.capability_analysis import CapabilityAnalyser, CapabilityAnalysis
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import (
    AgentSelector,
    NoAgentForCapabilityError,
    UnknownAgentsError,
)
from app.providers.registry import ProviderRegistry
from app.schemas.memory import DecisionCreate
from app.schemas.workflow import TaskRequest, WorkflowPlan
from app.services.model_pins import apply_routing_to_plan, model_id_from_parameters
from app.services.workflow_repository import WorkflowNotFoundError, WorkflowRepository
from app.workflows.engine import WorkflowEngine, WorkflowRun, restore_run

logger = get_logger(__name__)


class UnservableRequestError(RuntimeError):
    """Raised when no registered agent can satisfy part of the request."""


class UnknownModelOverrideError(RuntimeError):
    """Raised when a task pins a model that is not in the configured catalogue."""


class WorkflowNotResumableError(RuntimeError):
    """Raised when asked to resume a workflow that has already finished its work."""


class NodeControlError(RuntimeError):
    """Raised when a node cannot accept the requested control action."""


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    workflow: WorkflowRecord
    run: WorkflowRun


@dataclass(frozen=True, slots=True)
class PreparedWorkflow:
    """A planned, persisted workflow that has not started running."""

    task_id: uuid.UUID
    workflow_id: uuid.UUID
    plan: WorkflowPlan
    budget_usd: float | None = None


@dataclass(frozen=True, slots=True)
class PlanPreviewResult:
    """A plan that has not been executed, with its worst-case cost."""

    analysis: CapabilityAnalysis
    plan: WorkflowPlan
    #: Sum of the selected agents' cost ceilings: the most this workflow could spend.
    estimated_max_cost_usd: float


class OrchestrationService:
    def __init__(
        self,
        analyser: CapabilityAnalyser,
        selector: AgentSelector,
        planner: WorkflowPlanner,
        engine: WorkflowEngine,
        repository: WorkflowRepository,
        providers: ProviderRegistry | None = None,
    ) -> None:
        self._analyser = analyser
        self._selector = selector
        self._planner = planner
        self._engine = engine
        self._repository = repository
        self._providers = providers

    async def submit(self, request: TaskRequest, *, owner_id: str = "operator") -> OrchestrationResult:
        """Plan and execute in one call. The caller waits for the whole workflow."""
        prepared = await self.prepare(request, owner_id=owner_id)
        run = await self.execute(prepared)
        refreshed = await self._repository.get_workflow(prepared.workflow_id)
        return OrchestrationResult(workflow=refreshed, run=run)

    async def prepare(
        self, request: TaskRequest, *, owner_id: str = "operator"
    ) -> PreparedWorkflow:
        """Analyse, select, plan, and persist — without executing anything.

        Separate from execution so a client can be handed a workflow id and a graph to
        render immediately, while the agents run elsewhere. A user watching an empty
        screen cannot tell "thinking" from "broken".
        """
        analysis = await self._analyser.analyse(request.request)
        self._validate_routing_models(request)

        try:
            selection = await self._selector.select(
                analysis.required,
                agent_ids=frozenset(request.agent_ids) if request.agent_ids else None,
            )
        except UnknownAgentsError as exc:
            raise UnservableRequestError(str(exc)) from exc
        except NoAgentForCapabilityError as exc:
            # The task is still recorded: a request the platform cannot serve is useful
            # evidence of a coverage gap, not something to discard.
            task = await self._repository.create_task(request, owner_id=owner_id)
            await self._repository.set_task_status(task.id, TaskStatus.FAILED)
            logger.warning(
                "request_unservable",
                task_id=str(task.id),
                uncovered=sorted(capability.value for capability in exc.uncovered),
            )
            raise UnservableRequestError(str(exc)) from exc

        plan = self._planner.plan(
            request.request, analysis, selection, require_approval=request.require_approval
        )
        plan = apply_routing_to_plan(plan, request)

        task = await self._repository.create_task(request, owner_id=owner_id)
        workflow = await self._repository.create_workflow(task.id, plan, owner_id=owner_id)
        await self._record_selection_decision(workflow.id, plan, request)
        await self._record_pin_routing_decision(workflow.id, plan, request)

        logger.info(
            "task_submitted",
            task_id=str(task.id),
            workflow_id=str(workflow.id),
            required_capabilities=sorted(c.value for c in analysis.required),
            selected_agents=list(selection.agent_ids),
            routing_strategy=request.routing_strategy.value,
            shared_model=request.shared_model,
            model_overrides=dict(request.model_overrides),
            analysis_source=analysis.source,
        )
        return PreparedWorkflow(
            task_id=task.id,
            workflow_id=workflow.id,
            plan=plan,
            budget_usd=request.max_cost_usd,
        )

    async def execute(self, prepared: PreparedWorkflow) -> WorkflowRun:
        return await self._engine.run(
            prepared.workflow_id,
            prepared.task_id,
            prepared.plan,
            budget_usd=prepared.budget_usd,
        )

    async def resume(self, workflow_id: uuid.UUID) -> OrchestrationResult:
        """Continue a workflow that was cancelled or interrupted.

        The graph is loaded from the database rather than re-planned: re-planning could
        silently produce a different shape than the one the user was shown, and a
        resumed run that quietly changes its mind is worse than one that never resumed.
        Completed nodes are not run again, so no work is paid for twice.
        """
        workflow = await self._repository.get_workflow(workflow_id)
        # Status comes back from the database as a string; identity comparison against
        # the enum would silently fail and try to resume a finished run.
        if workflow.status == WorkflowStatus.COMPLETED:
            raise WorkflowNotResumableError(f"workflow '{workflow_id}' has already completed")

        plan = await self._repository.load_plan(workflow_id)
        await self._repository.prepare_resume(workflow_id)
        results, skipped, attempts = await self._repository.completed_state(workflow_id)
        state = restore_run(workflow_id, plan, results, skipped, attempts)

        budget = workflow.task.max_cost_usd if workflow.task is not None else None
        logger.info(
            "workflow_resumed",
            workflow_id=str(workflow_id),
            already_completed=sorted(results),
            already_skipped=sorted(skipped),
        )

        run = await self._engine.run(
            workflow_id, workflow.task_id, plan, budget_usd=budget, run=state
        )
        refreshed = await self._repository.get_workflow(workflow_id)
        return OrchestrationResult(workflow=refreshed, run=run)

    async def approve_node(
        self,
        workflow_id: uuid.UUID,
        node_key: str,
        *,
        decided_by: str,
        reason: str | None = None,
        continue_run: bool = True,
    ) -> OrchestrationResult:
        node = await self._require_node(workflow_id, node_key, {NodeStatus.AWAITING_APPROVAL})
        await self._repository.record_approval(
            workflow_id, node.node_key, approved=True, decided_by=decided_by, reason=reason
        )
        await DecisionService(self._repository._session).record(
            DecisionCreate(
                kind=DecisionKind.APPROVAL,
                actor_id=decided_by,
                agent_id=node.agent_id,
                workflow_id=workflow_id,
                node_key=node.node_key,
                title=f"Approved {node.node_key}",
                summary=reason,
                payload={"approved": True},
                tags=("approval", "approved"),
            )
        )
        await self._repository.commit()
        logger.info(
            "node_approved",
            workflow_id=str(workflow_id),
            node_key=node_key,
            decided_by=decided_by,
        )
        return await self._continue_after_control(workflow_id, continue_run=continue_run)

    async def reject_node(
        self,
        workflow_id: uuid.UUID,
        node_key: str,
        *,
        decided_by: str,
        reason: str | None = None,
        continue_run: bool = True,
    ) -> OrchestrationResult:
        node = await self._require_node(workflow_id, node_key, {NodeStatus.AWAITING_APPROVAL})
        reject_reason = reason or f"rejected by {decided_by}"
        await self._repository.record_approval(
            workflow_id,
            node.node_key,
            approved=False,
            decided_by=decided_by,
            reason=reject_reason,
        )
        await DecisionService(self._repository._session).record(
            DecisionCreate(
                kind=DecisionKind.APPROVAL,
                actor_id=decided_by,
                agent_id=node.agent_id,
                workflow_id=workflow_id,
                node_key=node.node_key,
                title=f"Rejected {node.node_key}",
                summary=reject_reason,
                payload={"approved": False},
                tags=("approval", "rejected"),
            )
        )
        await self._repository.commit()
        logger.info(
            "node_rejected",
            workflow_id=str(workflow_id),
            node_key=node_key,
            decided_by=decided_by,
        )
        # Continue so dependents can skip rather than hang waiting on a node that will
        # never run.
        return await self._continue_after_control(workflow_id, continue_run=continue_run)

    async def retry_node(
        self, workflow_id: uuid.UUID, node_key: str, *, continue_run: bool = True
    ) -> OrchestrationResult:
        node = await self._require_node(workflow_id, node_key, {NodeStatus.FAILED})
        plan = await self._repository.load_plan(workflow_id)
        await self._repository.reopen_node(workflow_id, node.node_key)
        for descendant in plan.descendants_of(node.node_key):
            await self._repository.reopen_node(workflow_id, descendant)
        await self._repository.commit()
        logger.info("node_retry_requested", workflow_id=str(workflow_id), node_key=node_key)
        return await self._continue_after_control(workflow_id, continue_run=continue_run)

    async def skip_node(
        self,
        workflow_id: uuid.UUID,
        node_key: str,
        *,
        reason: str | None = None,
        continue_run: bool = True,
    ) -> OrchestrationResult:
        node = await self._require_node(
            workflow_id,
            node_key,
            {
                NodeStatus.WAITING,
                NodeStatus.READY,
                NodeStatus.FAILED,
                NodeStatus.AWAITING_APPROVAL,
            },
        )
        await self._repository.skip_node(
            workflow_id, node.node_key, reason or "skipped by operator"
        )
        await self._repository.commit()
        logger.info("node_skipped_by_operator", workflow_id=str(workflow_id), node_key=node_key)
        return await self._continue_after_control(workflow_id, continue_run=continue_run)

    async def _continue_after_control(
        self, workflow_id: uuid.UUID, *, continue_run: bool
    ) -> OrchestrationResult:
        if continue_run:
            return await self.resume(workflow_id)
        workflow = await self._repository.get_workflow(workflow_id)
        return OrchestrationResult(
            workflow=workflow,
            run=WorkflowRun(workflow_id=workflow_id, status=WorkflowStatus(workflow.status)),
        )

    async def _require_idle_workflow(self, workflow_id: uuid.UUID) -> WorkflowRecord:
        workflow = await self._repository.get_workflow(workflow_id)
        if workflow.status == WorkflowStatus.RUNNING:
            raise NodeControlError(
                "cannot change a node while the workflow is running; cancel it first"
            )
        return workflow

    async def _require_node(
        self, workflow_id: uuid.UUID, node_key: str, allowed: set[NodeStatus]
    ) -> WorkflowNodeRecord:
        await self._require_idle_workflow(workflow_id)
        try:
            node = await self._repository.get_node(workflow_id, node_key)
        except WorkflowNotFoundError as exc:
            raise NodeControlError(str(exc)) from exc
        if NodeStatus(node.status) not in allowed:
            raise NodeControlError(
                f"node '{node_key}' is {node.status}, expected "
                f"{sorted(status.value for status in allowed)}"
            )
        return node

    async def plan_only(self, request: TaskRequest) -> PlanPreviewResult:
        """Analyse and plan without executing.

        Exposed so a user can see which agents a request would activate, and the most
        it could cost, before committing to the spend.
        """
        analysis = await self._analyser.analyse(request.request)
        self._validate_routing_models(request)
        try:
            selection = await self._selector.select(
                analysis.required,
                agent_ids=frozenset(request.agent_ids) if request.agent_ids else None,
            )
        except (NoAgentForCapabilityError, UnknownAgentsError) as exc:
            raise UnservableRequestError(str(exc)) from exc

        plan = self._planner.plan(
            request.request, analysis, selection, require_approval=request.require_approval
        )
        plan = apply_routing_to_plan(plan, request)
        ceiling = sum(
            selection.definitions[agent_id].limits.max_cost_usd for agent_id in selection.chosen
        )
        return PlanPreviewResult(
            analysis=analysis, plan=plan, estimated_max_cost_usd=round(ceiling, 4)
        )

    def _validate_routing_models(self, request: TaskRequest) -> None:
        if self._providers is None:
            return
        known = {model.id for model in self._providers.available_models()}
        candidates: list[str] = []
        if request.shared_model:
            candidates.append(request.shared_model)
        candidates.extend(request.model_overrides.values())
        unknown = sorted({model_id for model_id in candidates if model_id not in known})
        if unknown:
            raise UnknownModelOverrideError(f"unknown or unconfigured models: {', '.join(unknown)}")

    async def _record_selection_decision(
        self, workflow_id: uuid.UUID, plan: WorkflowPlan, request: TaskRequest
    ) -> None:
        selection = plan.selection
        if selection is None:
            return
        chosen = ", ".join(selection.selected) or "(none)"
        excluded_n = len(selection.excluded)
        await DecisionService(self._repository._session).record(
            DecisionCreate(
                kind=DecisionKind.SELECTION,
                actor_id="orchestrator",
                workflow_id=workflow_id,
                title="Agent selection",
                summary=selection.reasoning
                or f"Selected {chosen}"
                + (f"; excluded {excluded_n}" if excluded_n else ""),
                payload={
                    "required_capabilities": [c.value for c in selection.required_capabilities],
                    "selected": list(selection.selected),
                    "excluded": dict(selection.excluded),
                    "routing_strategy": request.routing_strategy.value,
                    "agent_ids": list(request.agent_ids) if request.agent_ids else None,
                },
                tags=("selection", "auto"),
                importance=0.85,
            )
        )

    async def _record_pin_routing_decision(
        self, workflow_id: uuid.UUID, plan: WorkflowPlan, request: TaskRequest
    ) -> None:
        """Record One/Mixed (and any baked node pins) as a routing decision at plan time."""
        node_pins = {
            node.key: model_id
            for node in plan.nodes
            if (model_id := model_id_from_parameters(dict(node.parameters))) is not None
        }
        if request.routing_strategy is RoutingStrategy.AUTO and not node_pins:
            return
        await DecisionService(self._repository._session).record(
            DecisionCreate(
                kind=DecisionKind.ROUTING,
                actor_id="orchestrator",
                workflow_id=workflow_id,
                title=f"Model routing ({request.routing_strategy.value})",
                summary=(
                    f"strategy={request.routing_strategy.value}"
                    + (f"; shared={request.shared_model}" if request.shared_model else "")
                    + (f"; pins={len(node_pins)}" if node_pins else "")
                ),
                payload={
                    "strategy": request.routing_strategy.value,
                    "shared_model": request.shared_model,
                    "model_overrides": dict(request.model_overrides),
                    "node_pins": node_pins,
                },
                tags=("routing", "pin", request.routing_strategy.value),
                importance=0.8,
            )
        )


def workflow_is_finished(status: WorkflowStatus) -> bool:
    return status in {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }
