"""Persistence for tasks, workflows, and executions.

All durable state goes through here so the workflow engine never writes SQL and the
storage shape can change without touching orchestration logic. Every state transition
is a write, which is what makes a workflow resumable after a process dies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.metrics import process_metrics
from app.domain.enums import (
    Capability,
    ExecutionStatus,
    NodeStatus,
    TaskStatus,
    WorkflowStatus,
)
from app.models.workflow import (
    AgentResultRecord,
    ExecutionRecord,
    TaskRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
    WorkflowRecord,
)
from app.schemas.execution import AgentOutput
from app.schemas.workflow import (
    AgentSelection,
    EdgeCondition,
    FeedbackRule,
    TaskRequest,
    WorkflowEdge,
    WorkflowNode,
    WorkflowPlan,
)


class WorkflowNotFoundError(KeyError):
    pass


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        """Make everything written so far durable.

        The engine calls this between batches. Two reasons: a crash then costs at most
        one batch of work rather than the whole run, and a cancellation committed by
        another session becomes visible to the one executing.
        """
        await self._session.commit()

    # ---- tasks -------------------------------------------------------------

    async def create_task(self, request: TaskRequest, *, owner_id: str = "operator") -> TaskRecord:
        parameters = dict(request.parameters)
        if request.agent_ids is not None:
            parameters["agent_ids"] = list(request.agent_ids)
        parameters["routing_strategy"] = request.routing_strategy.value
        if request.shared_model:
            parameters["shared_model"] = request.shared_model
        if request.model_overrides:
            parameters["model_overrides"] = dict(request.model_overrides)
        task = TaskRecord(
            request=request.request,
            parameters=parameters,
            max_cost_usd=request.max_cost_usd,
            require_approval=request.require_approval,
            status=TaskStatus.PENDING,
            owner_id=owner_id,
        )
        self._session.add(task)
        await self._session.flush()
        return task

    async def set_task_status(self, task_id: uuid.UUID, status: TaskStatus) -> None:
        task = await self._session.get(TaskRecord, task_id)
        if task is not None:
            task.status = status
            await self._session.flush()

    # ---- workflows ---------------------------------------------------------

    async def create_workflow(
        self, task_id: uuid.UUID, plan: WorkflowPlan, *, owner_id: str = "operator"
    ) -> WorkflowRecord:
        """Persist a plan as a workflow graph.

        Nodes and edges are written together with the workflow so a caller can never
        observe a workflow whose graph is half-written.
        """
        workflow = WorkflowRecord(
            task_id=task_id,
            status=WorkflowStatus.PENDING,
            selection=plan.selection.model_dump(mode="json") if plan.selection else {},
            owner_id=owner_id,
        )
        self._session.add(workflow)
        await self._session.flush()

        for position, node in enumerate(plan.nodes):
            self._session.add(
                WorkflowNodeRecord(
                    workflow_id=workflow.id,
                    node_key=node.key,
                    agent_id=node.agent_id,
                    objective=node.objective,
                    parameters=node.parameters,
                    satisfies=[capability.value for capability in node.satisfies],
                    status=node.status,
                    requires_approval=node.requires_approval,
                    join_policy=node.join_policy,
                    feedback=node.feedback.model_dump(mode="json") if node.feedback else None,
                    position=position,
                )
            )
        for edge in plan.edges:
            self._session.add(
                WorkflowEdgeRecord(
                    workflow_id=workflow.id,
                    source_key=edge.source,
                    target_key=edge.target,
                    condition=edge.condition.model_dump(mode="json") if edge.condition else None,
                    pass_payload=edge.pass_payload,
                )
            )
        await self._session.flush()
        return workflow

    async def get_workflow(
        self, workflow_id: uuid.UUID, *, owner_id: str | None = None
    ) -> WorkflowRecord:
        statement = (
            select(WorkflowRecord)
            .where(WorkflowRecord.id == workflow_id)
            .options(
                selectinload(WorkflowRecord.nodes).selectinload(WorkflowNodeRecord.executions),
                selectinload(WorkflowRecord.edges),
                selectinload(WorkflowRecord.task),
            )
        )
        if owner_id is not None:
            statement = statement.where(WorkflowRecord.owner_id == owner_id)
        result = await self._session.execute(statement)
        workflow = result.scalar_one_or_none()
        if workflow is None:
            raise WorkflowNotFoundError(f"workflow '{workflow_id}' not found")
        return workflow

    async def list_workflows(
        self, *, limit: int = 50, owner_id: str | None = None
    ) -> list[WorkflowRecord]:
        statement = (
            select(WorkflowRecord)
            .order_by(WorkflowRecord.created_at.desc())
            .limit(limit)
            .options(
                selectinload(WorkflowRecord.nodes),
                selectinload(WorkflowRecord.edges),
                selectinload(WorkflowRecord.task),
            )
        )
        if owner_id is not None:
            statement = statement.where(WorkflowRecord.owner_id == owner_id)
        result = await self._session.execute(statement)
        return list(result.scalars())

    async def start_workflow(self, workflow_id: uuid.UUID) -> None:
        workflow = await self._session.get(WorkflowRecord, workflow_id)
        if workflow is not None:
            workflow.status = WorkflowStatus.RUNNING
            if workflow.started_at is None:
                workflow.started_at = datetime.now(UTC)
            await self._session.flush()

    async def finish_workflow(
        self,
        workflow_id: uuid.UUID,
        status: WorkflowStatus,
        *,
        final_result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> None:
        workflow = await self._session.get(WorkflowRecord, workflow_id)
        if workflow is None:
            return
        workflow.status = status
        if status in _TERMINAL_WORKFLOW_STATUSES:
            workflow.completed_at = datetime.now(UTC)
        else:
            workflow.completed_at = None
        if final_result is not None:
            workflow.final_result = final_result
        if error is not None:
            workflow.error = error
        await self._session.flush()

    # ---- nodes -------------------------------------------------------------

    async def get_node(self, workflow_id: uuid.UUID, node_key: str) -> WorkflowNodeRecord:
        statement = select(WorkflowNodeRecord).where(
            WorkflowNodeRecord.workflow_id == workflow_id,
            WorkflowNodeRecord.node_key == node_key,
        )
        result = await self._session.execute(statement)
        node = result.scalar_one_or_none()
        if node is None:
            raise WorkflowNotFoundError(f"node '{node_key}' not found in workflow {workflow_id}")
        return node

    async def set_node_status(
        self,
        workflow_id: uuid.UUID,
        node_key: str,
        status: NodeStatus,
        *,
        skip_reason: str | None = None,
    ) -> None:
        node = await self.get_node(workflow_id, node_key)
        node.status = status
        if skip_reason is not None:
            node.skip_reason = skip_reason
        await self._session.flush()

    # ---- executions --------------------------------------------------------

    async def record_execution(
        self, workflow_id: uuid.UUID, output: AgentOutput, *, raw_output: str | None = None
    ) -> ExecutionRecord:
        """Write one attempt and its result, and roll the node and workflow forward.

        Writing the attempt, the node state, and the accumulated cost in one call keeps
        them consistent: a crash between them would otherwise leave a node that looks
        complete but has no result, or spend that is never counted.
        """
        node = await self.get_node(workflow_id, output.node_key)
        node.attempts = max(node.attempts, output.attempt)

        execution = ExecutionRecord(
            node_id=node.id,
            attempt=output.attempt,
            status=output.status,
            provider_id=output.provider,
            model_id=output.model,
            input_tokens=output.usage.input_tokens,
            output_tokens=output.usage.output_tokens,
            cost_usd=output.cost_usd,
            latency_ms=output.latency_ms,
            error_kind=output.error.kind.value if output.error else None,
            error_message=output.error.message if output.error else None,
            started_at=output.started_at,
            completed_at=output.completed_at,
        )
        self._session.add(execution)
        await self._session.flush()

        self._session.add(
            AgentResultRecord(
                execution_id=execution.id,
                payload=output.payload,
                summary=output.summary,
                schema_valid=output.status is not ExecutionStatus.INVALID_OUTPUT,
                validation_error=(
                    output.error.message
                    if output.error and output.status is ExecutionStatus.INVALID_OUTPUT
                    else None
                ),
                # Raw text is kept only when validation failed, so debugging is possible
                # without storing every completion by default.
                raw_output=(
                    raw_output if output.status is ExecutionStatus.INVALID_OUTPUT else None
                ),
            )
        )

        if output.succeeded:
            node.status = NodeStatus.COMPLETED
            node.result_payload = output.payload
        elif output.status is ExecutionStatus.CANCELLED:
            node.status = NodeStatus.CANCELLED

        workflow = await self._session.get(WorkflowRecord, workflow_id)
        if workflow is not None:
            workflow.total_cost_usd += output.cost_usd

        process_metrics.observe(
            status=output.status.value,
            provider=output.provider,
            cost_usd=output.cost_usd,
            input_tokens=output.usage.input_tokens,
            output_tokens=output.usage.output_tokens,
            attempt=output.attempt,
            error_kind=output.error.kind.value if output.error else None,
        )

        await self._session.flush()
        return execution

    async def mark_node_failed(self, workflow_id: uuid.UUID, node_key: str) -> None:
        await self.set_node_status(workflow_id, node_key, NodeStatus.FAILED)

    async def skip_node(self, workflow_id: uuid.UUID, node_key: str, reason: str) -> None:
        """Record a node as deliberately not run.

        Skipping is a success state in this product, so the reason is persisted next to
        the status: a node that shows "skipped" with no explanation looks like a bug.
        """
        await self.set_node_status(workflow_id, node_key, NodeStatus.SKIPPED, skip_reason=reason)

    async def get_approval(self, workflow_id: uuid.UUID, node_key: str) -> dict[str, object] | None:
        node = await self.get_node(workflow_id, node_key)
        return dict(node.approval) if node.approval else None

    async def record_approval(
        self,
        workflow_id: uuid.UUID,
        node_key: str,
        *,
        approved: bool,
        decided_by: str,
        reason: str | None = None,
    ) -> None:
        node = await self.get_node(workflow_id, node_key)
        node.approval = {
            "approved": approved,
            "decided_by": decided_by,
            "reason": reason,
            "decided_at": datetime.now(UTC).isoformat(),
        }
        if approved:
            node.status = NodeStatus.WAITING
            node.skip_reason = None
        else:
            node.status = NodeStatus.SKIPPED
            node.skip_reason = reason or f"rejected by {decided_by}"
        await self._session.flush()

    async def pause_for_approval(self, workflow_id: uuid.UUID) -> None:
        workflow = await self._session.get(WorkflowRecord, workflow_id)
        if workflow is None:
            return
        workflow.status = WorkflowStatus.AWAITING_APPROVAL
        await self._session.flush()

    async def reopen_node(self, workflow_id: uuid.UUID, node_key: str) -> None:
        """Return a node to the waiting state so it can run again.

        Used when a downstream verdict sends work back. Previous attempts and their
        costs stay on the record — the history of what was tried is the point — but the
        node's result is cleared so nothing downstream reads a superseded answer.
        """
        node = await self.get_node(workflow_id, node_key)
        node.status = NodeStatus.WAITING
        node.result_payload = {}
        node.skip_reason = None
        await self._session.flush()

    async def workflow_cost(self, workflow_id: uuid.UUID) -> float:
        workflow = await self._session.get(WorkflowRecord, workflow_id)
        return workflow.total_cost_usd if workflow else 0.0

    # ---- cancellation ------------------------------------------------------

    async def request_cancellation(self, workflow_id: uuid.UUID) -> bool:
        """Ask a workflow to stop. Returns False if it had already finished.

        A request rather than a state change: the engine may be mid-call in another
        process, and only it can say what actually stopped.
        """
        workflow = await self._session.get(WorkflowRecord, workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(f"workflow '{workflow_id}' not found")
        if workflow.status in _TERMINAL_WORKFLOW_STATUSES:
            return False
        workflow.cancel_requested = True
        await self._session.flush()
        return True

    async def cancellation_requested(self, workflow_id: uuid.UUID) -> bool:
        """Read the flag straight from the database.

        A column select rather than an entity load, because the engine may be holding a
        stale copy of the workflow in its identity map while the request to cancel was
        committed by a different session.
        """
        statement = select(WorkflowRecord.cancel_requested).where(WorkflowRecord.id == workflow_id)
        result = await self._session.execute(statement)
        return bool(result.scalar_one_or_none())

    async def cancel_unfinished_nodes(self, workflow_id: uuid.UUID) -> list[str]:
        """Mark everything not yet finished as cancelled, and say which those were."""
        statement = select(WorkflowNodeRecord).where(
            WorkflowNodeRecord.workflow_id == workflow_id,
            WorkflowNodeRecord.status.in_(
                [
                    NodeStatus.WAITING,
                    NodeStatus.READY,
                    NodeStatus.RUNNING,
                    NodeStatus.AWAITING_APPROVAL,
                ]
            ),
        )
        result = await self._session.execute(statement)
        cancelled = []
        for node in result.scalars():
            node.status = NodeStatus.CANCELLED
            cancelled.append(node.node_key)
        await self._session.flush()
        return cancelled

    # ---- resume ------------------------------------------------------------

    async def load_plan(self, workflow_id: uuid.UUID) -> WorkflowPlan:
        """Rebuild the plan from persisted rows.

        Resume depends on this: the graph has to come from the database, not from
        re-planning, or a resumed workflow could silently execute a different shape than
        the one the user was shown.
        """
        workflow = await self.get_workflow(workflow_id)
        nodes = tuple(
            WorkflowNode(
                key=node.node_key,
                agent_id=node.agent_id,
                objective=node.objective,
                parameters=node.parameters,
                satisfies=tuple(Capability(value) for value in node.satisfies),
                requires_approval=node.requires_approval,
                join_policy="any" if node.join_policy == "any" else "all",
                feedback=FeedbackRule.model_validate(node.feedback) if node.feedback else None,
                status=NodeStatus(node.status),
                skip_reason=node.skip_reason,
            )
            for node in sorted(workflow.nodes, key=lambda record: record.position)
        )
        edges = tuple(
            WorkflowEdge(
                source=edge.source_key,
                target=edge.target_key,
                condition=(
                    EdgeCondition.model_validate(edge.condition) if edge.condition else None
                ),
                pass_payload=edge.pass_payload,
            )
            for edge in workflow.edges
        )
        selection = (
            AgentSelection.model_validate(workflow.selection) if workflow.selection else None
        )
        return WorkflowPlan(nodes=nodes, edges=edges, selection=selection)

    async def completed_state(
        self, workflow_id: uuid.UUID
    ) -> tuple[dict[str, dict[str, object]], dict[str, str], dict[str, int]]:
        """What the workflow already knows: results, skips, and attempts used.

        Returned as plain data so a resumed run starts from the database rather than
        from whatever an earlier process happened to hold in memory.
        """
        workflow = await self.get_workflow(workflow_id)
        results: dict[str, dict[str, object]] = {}
        skipped: dict[str, str] = {}
        attempts: dict[str, int] = {}
        for node in workflow.nodes:
            attempts[node.node_key] = node.attempts
            if node.status == NodeStatus.COMPLETED:
                results[node.node_key] = dict(node.result_payload)
            elif node.status == NodeStatus.SKIPPED:
                skipped[node.node_key] = node.skip_reason or "skipped"
        return results, skipped, attempts

    async def prepare_resume(self, workflow_id: uuid.UUID) -> None:
        """Clear cancellation and reopen nodes that never reached a terminal state."""
        workflow = await self._session.get(WorkflowRecord, workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(f"workflow '{workflow_id}' not found")
        workflow.cancel_requested = False
        workflow.error = None
        workflow.completed_at = None

        statement = select(WorkflowNodeRecord).where(
            WorkflowNodeRecord.workflow_id == workflow_id,
            WorkflowNodeRecord.status.in_(
                [NodeStatus.CANCELLED, NodeStatus.RUNNING, NodeStatus.READY, NodeStatus.FAILED]
            ),
        )
        result = await self._session.execute(statement)
        for node in result.scalars():
            node.status = NodeStatus.WAITING
        await self._session.flush()


_TERMINAL_WORKFLOW_STATUSES = frozenset(
    {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
)
