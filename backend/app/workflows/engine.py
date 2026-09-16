"""The workflow execution engine.

Responsibilities: decide which nodes are runnable, decide which are unnecessary, build
each node's input from its upstream results, execute it with its retry policy, persist
every transition, route a downstream verdict back upstream when one is configured, and
stop when the graph is finished, cancelled, or out of budget.

The engine is dependency-driven rather than list-driven — it repeatedly asks "which
nodes have all their dependencies resolved?" — so sequential execution is the degenerate
case of a chain, parallelism is a property of dispatch, and a conditional skip is just a
dependency resolved in the negative.

Two decisions shape everything here:

* **Skipping is a success state.** Deciding an agent is unnecessary is the product's
  core behaviour, so a skip carries a reason, is persisted, and does not fail a run.
* **Progress is committed after every batch.** A crash then costs at most one batch, and
  a cancellation requested by another process becomes visible to this one.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field

from app.agents.registry import AgentRegistry
from app.core.logging import get_logger
from app.domain.enums import DecisionKind, ExecutionStatus, NodeStatus, TaskStatus, WorkflowStatus
from app.messaging.store import DecisionService
from app.schemas.agent import AgentDefinition
from app.schemas.execution import AgentInput, AgentOutput, UpstreamResult
from app.schemas.memory import DecisionCreate
from app.schemas.workflow import FeedbackRule, WorkflowNode, WorkflowPlan
from app.services import hive as hive_service
from app.services.agent_executor import AgentExecutor, ExecutionContext
from app.services.collaboration import Collaboration
from app.services.model_pins import model_id_from_parameters, pin_model
from app.services.workflow_repository import WorkflowRepository
from app.workflows.conditions import describe, evaluate, resolve_path
from app.workflows.synthesis import synthesise

logger = get_logger(__name__)

_MAX_FEEDBACK_CHARS = 2_000


@dataclass(slots=True)
class WorkflowRun:
    """The outcome of executing a workflow, and the state the loop reasons over."""

    workflow_id: uuid.UUID
    status: WorkflowStatus
    #: Last attempt per node that produced a result.
    outputs: dict[str, AgentOutput] = field(default_factory=dict)
    #: Node key to the reason it was not run.
    skipped: dict[str, str] = field(default_factory=dict)
    #: Attempts already spent per node, including those from earlier repair cycles.
    attempts: dict[str, int] = field(default_factory=dict)
    #: Feedback waiting to be handed to a node on its next run.
    pending_feedback: dict[str, str] = field(default_factory=dict)
    #: Repair cycles spent per node, which is what bounds the feedback loop.
    repairs: dict[str, int] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    error: str | None = None

    @property
    def completed_nodes(self) -> tuple[str, ...]:
        return tuple(key for key, output in self.outputs.items() if output.succeeded)

    def resolved(self, node_key: str) -> bool:
        """Whether this node has reached an outcome, of any kind."""
        return node_key in self.outputs or node_key in self.skipped


def restore_run(
    workflow_id: uuid.UUID,
    plan: WorkflowPlan,
    results: dict[str, dict[str, object]],
    skipped: dict[str, str],
    attempts: dict[str, int],
) -> WorkflowRun:
    """Rebuild in-memory run state from what the database already knows.

    Resume uses this. The reconstructed outputs carry payloads and nothing else —
    latency, provider, and cost belong to the original attempt and are already recorded
    against it, so re-reporting them here would double-count.
    """
    outputs = {
        key: AgentOutput(
            agent_id=plan.node(key).agent_id,
            node_key=key,
            status=ExecutionStatus.SUCCEEDED,
            payload=payload,
        )
        for key, payload in results.items()
    }
    return WorkflowRun(
        workflow_id=workflow_id,
        status=WorkflowStatus.RUNNING,
        outputs=outputs,
        skipped=dict(skipped),
        attempts=dict(attempts),
    )


class WorkflowEngine:
    def __init__(
        self,
        registry: AgentRegistry,
        executor: AgentExecutor,
        repository: WorkflowRepository,
        *,
        collaboration: Collaboration | None = None,
        max_parallel_agents: int = 4,
        max_repair_cycles: int = 1,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._repository = repository
        self._collaboration = collaboration
        # Bounded so a wide workflow cannot open unlimited provider connections or
        # trip a rate limit that would fail every branch at once.
        self._max_parallel = max(1, max_parallel_agents)
        # Bounded because a coding agent and a testing agent can disagree forever, and
        # each round of that argument costs real money.
        self._max_repair_cycles = max(0, max_repair_cycles)

    async def run(
        self,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
        plan: WorkflowPlan,
        *,
        budget_usd: float | None = None,
        run: WorkflowRun | None = None,
    ) -> WorkflowRun:
        """Execute a plan to completion, or to its first hard failure.

        ``run`` carries state from a previous, interrupted execution; when it is given,
        nodes that already finished are not run again.
        """
        await self._repository.start_workflow(workflow_id)
        await self._repository.set_task_status(task_id, TaskStatus.RUNNING)

        state = run or WorkflowRun(workflow_id=workflow_id, status=WorkflowStatus.RUNNING)
        state.status = WorkflowStatus.RUNNING
        remaining_budget = budget_usd
        if budget_usd is not None:
            spent = await self._repository.workflow_cost(workflow_id)
            remaining_budget = max(0.0, budget_usd - spent)

        while True:
            if await self._repository.cancellation_requested(workflow_id):
                return await self._finish_cancelled(workflow_id, task_id, state)

            ready = self._ready_nodes(plan, state)
            if not ready:
                break

            runnable = await self._resolve_skips(ready, plan, state, workflow_id)
            if not runnable:
                # Everything ready was skipped; loop again, because their dependents may
                # now be skippable too.
                await self._repository.commit()
                continue

            gated, allowed = await self._partition_approval(runnable, plan, state, workflow_id)
            if gated and not allowed:
                return await self._pause_for_approval(workflow_id, task_id, state, gated, plan)
            if not allowed:
                # Every ready node was rejected; dependents may now be skippable.
                await self._repository.commit()
                continue

            attempts = await self._execute_batch(
                allowed, plan, state, task_id, workflow_id, remaining_budget
            )

            # Persistence is serialised even though execution was concurrent: one
            # AsyncSession is not safe for concurrent use, and the wall-clock time is in
            # the provider calls, not in these writes.
            failures: list[AgentOutput] = []
            for node_attempts in attempts:
                final = node_attempts[-1]
                state.outputs[final.node_key] = final
                state.attempts[final.node_key] = state.attempts.get(final.node_key, 0) + len(
                    node_attempts
                )

                for output in node_attempts:
                    state.total_cost_usd += output.cost_usd
                    if remaining_budget is not None:
                        remaining_budget = max(0.0, remaining_budget - output.cost_usd)
                    raw = None
                    if output.error is not None:
                        candidate = output.error.details.get("raw_output")
                        raw = candidate if isinstance(candidate, str) else None
                    await self._repository.record_execution(workflow_id, output, raw_output=raw)

                if not final.succeeded:
                    await self._repository.mark_node_failed(workflow_id, final.node_key)
                    failures.append(final)
                if self._collaboration is not None:
                    await self._collaboration.on_node_finished(
                        plan=plan, output=final, workflow_id=workflow_id, task_id=task_id
                    )

            await self._repository.commit()

            if failures:
                # Siblings that succeeded keep their persisted results: a failed branch
                # must not discard work that was paid for and completed. The workflow
                # still fails rather than returning a partial result that reads as whole.
                return await self._finish_failed(workflow_id, task_id, state, failures)

            await self._route_feedback(plan, state, workflow_id, task_id)

        return await self._finish_completed(workflow_id, task_id, plan, state)

    async def _pause_for_approval(
        self,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
        state: WorkflowRun,
        gated: tuple[str, ...],
        plan: WorkflowPlan,
    ) -> WorkflowRun:
        """Stop scheduling until a human decides.

        In-flight siblings are not a concern here: we only pause when *every* currently
        ready node needs approval, so nothing else is running. Independent branches that
        did not need a gate have already completed and been persisted.
        """
        await self._repository.pause_for_approval(workflow_id)
        await self._repository.commit()
        state.status = WorkflowStatus.AWAITING_APPROVAL
        if self._collaboration is not None:
            for node_key in gated:
                await self._collaboration.on_approval_requested(
                    agent_id=plan.node(node_key).agent_id,
                    node_key=node_key,
                    workflow_id=workflow_id,
                )
        logger.info(
            "workflow_awaiting_approval",
            workflow_id=str(workflow_id),
            task_id=str(task_id),
            nodes=list(gated),
        )
        return state

    # ---- outcomes ----------------------------------------------------------

    async def _finish_completed(
        self,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
        plan: WorkflowPlan,
        state: WorkflowRun,
    ) -> WorkflowRun:
        final_result = self._final_result(plan, state)
        await self._repository.finish_workflow(
            workflow_id, WorkflowStatus.COMPLETED, final_result=final_result
        )
        await self._repository.set_task_status(task_id, TaskStatus.COMPLETED)
        await self._repository.commit()
        state.status = WorkflowStatus.COMPLETED
        if self._collaboration is not None:
            await self._collaboration.on_workflow_completed(workflow_id=workflow_id)

        logger.info(
            "workflow_completed",
            workflow_id=str(workflow_id),
            nodes_run=len(state.outputs),
            nodes_skipped=sorted(state.skipped),
            repairs=dict(state.repairs),
            total_cost_usd=round(state.total_cost_usd, 6),
        )
        return state

    async def _finish_failed(
        self,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
        state: WorkflowRun,
        failures: list[AgentOutput],
    ) -> WorkflowRun:
        failed = failures[0]
        message = (
            failed.error.message
            if failed.error
            else f"node '{failed.node_key}' failed with status {failed.status.value}"
        )
        await self._repository.finish_workflow(workflow_id, WorkflowStatus.FAILED, error=message)
        await self._repository.set_task_status(task_id, TaskStatus.FAILED)
        await self._repository.commit()
        state.status = WorkflowStatus.FAILED
        state.error = message

        logger.warning(
            "workflow_failed",
            workflow_id=str(workflow_id),
            failed_nodes=[output.node_key for output in failures],
            attempts=[state.attempts.get(output.node_key, 1) for output in failures],
            error_kind=failed.error.kind.value if failed.error else None,
            total_cost_usd=round(state.total_cost_usd, 6),
        )
        return state

    async def _finish_cancelled(
        self, workflow_id: uuid.UUID, task_id: uuid.UUID, state: WorkflowRun
    ) -> WorkflowRun:
        cancelled = await self._repository.cancel_unfinished_nodes(workflow_id)
        await self._repository.finish_workflow(
            workflow_id, WorkflowStatus.CANCELLED, error="cancelled on request"
        )
        await self._repository.set_task_status(task_id, TaskStatus.CANCELLED)
        await self._repository.commit()
        state.status = WorkflowStatus.CANCELLED
        state.error = "cancelled on request"

        logger.info(
            "workflow_cancelled",
            workflow_id=str(workflow_id),
            cancelled_nodes=cancelled,
            completed_nodes=list(state.completed_nodes),
            total_cost_usd=round(state.total_cost_usd, 6),
        )
        return state

    # ---- dispatch ----------------------------------------------------------

    async def _execute_batch(
        self,
        runnable: tuple[str, ...],
        plan: WorkflowPlan,
        state: WorkflowRun,
        task_id: uuid.UUID,
        workflow_id: uuid.UUID,
        remaining_budget: float | None,
    ) -> list[list[AgentOutput]]:
        """Run every runnable node concurrently, up to the fan-out limit.

        The budget passed to each member of a batch is the remainder *before* the batch
        ran, because concurrent calls cannot reserve against each other. A batch can
        therefore overshoot a workflow budget by at most the cost of its concurrent
        members and their retries; each agent's own hard ceiling still applies, and the
        real spend is recorded.

        Each element of the result is one node's attempts, oldest first.
        """
        prepared: list[tuple[AgentDefinition, AgentInput]] = []
        for node_key in runnable:
            node = plan.node(node_key)
            agent = await self._registry.get(node.agent_id)
            if model_id := model_id_from_parameters(dict(node.parameters)):
                agent = pin_model(agent, model_id)
            await self._repository.set_node_status(workflow_id, node_key, NodeStatus.RUNNING)
            notes = None
            if self._collaboration is not None:
                downstream = [
                    plan.node(edge.target).agent_id
                    for edge in plan.edges
                    if edge.source == node_key
                ]
                floor = tuple(dict.fromkeys(n.agent_id for n in plan.nodes))
                peer_ids = hive_service.peer_ids_on_floor(floor, agent.id)
                brief = await self._collaboration.context.brief(agent.id, workflow_id)
                notes = await self._collaboration.prepare_attempt(
                    agent=agent,
                    objective=node.objective,
                    peer_ids=peer_ids,
                    workflow_id=workflow_id,
                    task_id=task_id,
                    existing_notes=brief or None,
                )
                await self._collaboration.on_node_start(
                    agent_id=agent.id,
                    node_key=node_key,
                    workflow_id=workflow_id,
                    sending_to=downstream[0] if downstream else None,
                    objective=node.objective,
                )
            prepared.append(
                (
                    agent,
                    AgentInput(
                        task_id=task_id,
                        node_key=node_key,
                        agent_id=agent.id,
                        objective=node.objective,
                        parameters=node.parameters,
                        upstream=self._upstream_for(node_key, plan, state),
                        feedback=state.pending_feedback.pop(node_key, None),
                        context_notes=notes,
                    ),
                )
            )
        await self._repository.commit()

        context = ExecutionContext(remaining_budget_usd=remaining_budget)

        if len(prepared) == 1:
            agent, agent_input = prepared[0]
            return [await self._attempt_node(agent, agent_input, context, state)]

        semaphore = asyncio.Semaphore(self._max_parallel)

        async def run_one(agent: AgentDefinition, agent_input: AgentInput) -> list[AgentOutput]:
            async with semaphore:
                return await self._attempt_node(agent, agent_input, context, state)

        logger.info(
            "batch_dispatched",
            workflow_id=str(workflow_id),
            nodes=[agent_input.node_key for _, agent_input in prepared],
            max_parallel=self._max_parallel,
        )
        # The executor converts every failure into an AgentOutput, so gather cannot
        # raise here and one branch cannot cancel its siblings.
        return list(
            await asyncio.gather(*(run_one(agent, agent_input) for agent, agent_input in prepared))
        )

    async def _attempt_node(
        self,
        agent: AgentDefinition,
        agent_input: AgentInput,
        context: ExecutionContext,
        state: WorkflowRun,
    ) -> list[AgentOutput]:
        """Execute one node under its retry policy, returning every attempt.

        Retries are the agent's own declared policy rather than a global rule, because
        a cheap classifier and an expensive reasoning run do not deserve the same number
        of second chances. A non-retryable error stops immediately: retrying a bad API
        key or a malformed request only burns latency and money.

        Attempt numbers continue from any earlier repair cycle, so the recorded history
        reads as one sequence of tries rather than restarting at 1.
        """
        already_used = state.attempts.get(agent_input.node_key, 0)
        feedback = agent_input.feedback
        outputs: list[AgentOutput] = []

        for index in range(1, agent.retry_policy.max_attempts + 1):
            if delay := agent.retry_policy.backoff_for_attempt(index):
                await asyncio.sleep(delay)

            attempt_input = agent_input.model_copy(
                update={"attempt": already_used + index, "feedback": feedback}
            )
            output = await self._executor.execute(agent, attempt_input, context)
            outputs.append(output)
            await self._record_routing_decision(state.workflow_id, output)

            if output.succeeded:
                break
            if output.error is not None and not output.error.is_retryable:
                logger.info(
                    "retry_abandoned",
                    node_key=agent_input.node_key,
                    error_kind=output.error.kind.value,
                    reason="error is not retryable",
                )
                break
            if index < agent.retry_policy.max_attempts:
                feedback = self._retry_feedback(output) or feedback
                logger.info(
                    "retrying_node",
                    node_key=agent_input.node_key,
                    attempt=already_used + index,
                    next_attempt=already_used + index + 1,
                    error_kind=output.error.kind.value if output.error else None,
                )

        return outputs

    async def _record_routing_decision(
        self, workflow_id: uuid.UUID, output: AgentOutput
    ) -> None:
        """Persist why this attempt used its provider/model (and what else was eligible)."""
        if not output.routing_reason and not output.provider:
            return
        model_label = (
            f"{output.provider}:{output.model}"
            if output.provider and output.model
            else output.model or output.provider or "unknown"
        )
        await DecisionService(self._repository._session).record(
            DecisionCreate(
                kind=DecisionKind.ROUTING,
                actor_id="executor",
                agent_id=output.agent_id,
                workflow_id=workflow_id,
                node_key=output.node_key,
                title=f"Routed {output.node_key} → {model_label}",
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

    @staticmethod
    def _retry_feedback(output: AgentOutput) -> str | None:
        """Turn a failure into an instruction for the next attempt.

        Repeating an identical prompt after a schema violation tends to reproduce the
        violation. Telling the model what was wrong with its last answer is the cheapest
        available fix.
        """
        if output.status is ExecutionStatus.INVALID_OUTPUT and output.error is not None:
            return (
                f"Your previous response was rejected: {output.error.message}. "
                "Return only a JSON object matching the required schema."
            )
        return None

    # ---- scheduling --------------------------------------------------------

    @staticmethod
    def _ready_nodes(plan: WorkflowPlan, state: WorkflowRun) -> tuple[str, ...]:
        """Nodes not yet resolved whose dependencies have all reached an outcome.

        "Resolved" rather than "succeeded": a skipped dependency is a settled answer,
        and a node waiting on one would otherwise wait forever.
        """
        ready = []
        for node in plan.nodes:
            if state.resolved(node.key):
                continue
            if all(state.resolved(dependency) for dependency in plan.dependencies_of(node.key)):
                ready.append(node.key)
        return tuple(ready)

    async def _resolve_skips(
        self,
        ready: tuple[str, ...],
        plan: WorkflowPlan,
        state: WorkflowRun,
        workflow_id: uuid.UUID,
    ) -> tuple[str, ...]:
        """Separate the nodes that should run from the ones that should not.

        Deciding this before dispatch is the whole point of the product: an agent that
        is not needed costs nothing, and the user is told why it was left out.
        """
        runnable = []
        for node_key in ready:
            reason = self._skip_reason(plan.node(node_key), plan, state)
            if reason is None:
                runnable.append(node_key)
                continue
            state.skipped[node_key] = reason
            await self._repository.skip_node(workflow_id, node_key, reason)
            if self._collaboration is not None:
                await self._collaboration.on_skip(
                    agent_id=plan.node(node_key).agent_id,
                    node_key=node_key,
                    workflow_id=workflow_id,
                    reason=reason,
                )
            logger.info(
                "node_skipped",
                workflow_id=str(workflow_id),
                node_key=node_key,
                reason=reason,
            )
        return tuple(runnable)

    async def _partition_approval(
        self,
        runnable: tuple[str, ...],
        plan: WorkflowPlan,
        state: WorkflowRun,
        workflow_id: uuid.UUID,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Split ready nodes into those waiting on a person and those that may run.

        An approved node runs. A rejected node is skipped rather than executed — the
        human said no, and inventing a run they refused would be a serious bug.
        """
        gated: list[str] = []
        allowed: list[str] = []
        for node_key in runnable:
            node = plan.node(node_key)
            if not node.requires_approval:
                allowed.append(node_key)
                continue
            decision = await self._repository.get_approval(workflow_id, node_key)
            if decision is None:
                await self._repository.set_node_status(
                    workflow_id, node_key, NodeStatus.AWAITING_APPROVAL
                )
                gated.append(node_key)
            elif decision.get("approved") is True:
                allowed.append(node_key)
            else:
                actor = str(decision.get("decided_by") or "operator")
                reason = str(decision.get("reason") or f"rejected by {actor}")
                state.skipped[node_key] = reason
                await self._repository.skip_node(workflow_id, node_key, reason)
        return tuple(gated), tuple(allowed)

    @staticmethod
    def _skip_reason(node: WorkflowNode, plan: WorkflowPlan, state: WorkflowRun) -> str | None:
        """Why this node should not run, or None if it should.

        A node needs its incoming edges satisfied: the source produced a result, and any
        condition on the edge holds against that result. ``join_policy`` decides whether
        all of them or just one is enough — a report should still describe the branches
        that did run, while a fix has nothing to do if the audit found nothing.
        """
        incoming = [edge for edge in plan.edges if edge.target == node.key]
        if not incoming:
            return None

        unsatisfied: list[str] = []
        satisfied = 0
        for edge in incoming:
            if edge.source in state.skipped:
                unsatisfied.append(f"'{edge.source}' was skipped")
                continue
            output = state.outputs.get(edge.source)
            if output is None or not output.succeeded:
                unsatisfied.append(f"'{edge.source}' produced no result")
                continue
            if edge.condition is not None and not evaluate(edge.condition, output.payload):
                unsatisfied.append(describe(edge.condition, edge.source))
                continue
            satisfied += 1

        if node.join_policy == "any":
            return None if satisfied else "; ".join(unsatisfied)
        return None if not unsatisfied else "; ".join(unsatisfied)

    # ---- feedback ----------------------------------------------------------

    async def _route_feedback(
        self,
        plan: WorkflowPlan,
        state: WorkflowRun,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> bool:
        """Send a downstream verdict back upstream, if one fired.

        The graph stays acyclic: nothing is re-wired. A completed node is reopened, and
        everything computed from its output is reopened with it — otherwise the workflow
        would report results derived from an answer that has been superseded.
        """
        for node in plan.nodes:
            rule = node.feedback
            output = state.outputs.get(node.key)
            if rule is None or output is None or not output.succeeded:
                continue
            if not evaluate(rule.condition, output.payload):
                continue

            spent = state.repairs.get(rule.target, 0)
            if spent >= self._max_repair_cycles:
                # The verdict stands and is recorded. Arguing further costs money per
                # round and rarely converges.
                logger.info(
                    "repair_budget_exhausted",
                    workflow_id=str(workflow_id),
                    verdict_from=node.key,
                    target=rule.target,
                    cycles=spent,
                )
                continue

            state.repairs[rule.target] = spent + 1
            affected = (rule.target, *plan.descendants_of(rule.target))
            for key in affected:
                state.outputs.pop(key, None)
                state.skipped.pop(key, None)
                await self._repository.reopen_node(workflow_id, key)
            state.pending_feedback[rule.target] = self._feedback_text(rule, output)
            await self._repository.commit()
            if self._collaboration is not None:
                await self._collaboration.on_feedback(
                    from_agent=output.agent_id,
                    to_agent=plan.node(rule.target).agent_id,
                    workflow_id=workflow_id,
                    task_id=task_id,
                    message=state.pending_feedback[rule.target],
                )

            logger.info(
                "feedback_routed",
                workflow_id=str(workflow_id),
                verdict_from=node.key,
                target=rule.target,
                reopened=list(affected),
                cycle=spent + 1,
            )
            return True
        return False

    @staticmethod
    def _feedback_text(rule: FeedbackRule, output: AgentOutput) -> str:
        """The message the reopened node receives.

        The detail comes from the verdict's own payload rather than from prose written
        here, so the upstream agent is told what actually failed.
        """
        detail = resolve_path(output.payload, rule.detail_path) if rule.detail_path else None
        if detail is None or isinstance(detail, str) and not detail.strip():
            rendered = ""
        elif isinstance(detail, str):
            rendered = detail
        else:
            try:
                rendered = json.dumps(detail, default=str)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                rendered = str(detail)

        message = rule.message if not rendered else f"{rule.message}\n\n{rendered}"
        if len(message) > _MAX_FEEDBACK_CHARS:
            message = message[:_MAX_FEEDBACK_CHARS] + "\n[truncated]"
        return message

    # ---- hand-off ----------------------------------------------------------

    @staticmethod
    def _upstream_for(
        node_key: str, plan: WorkflowPlan, state: WorkflowRun
    ) -> tuple[UpstreamResult, ...]:
        """Collect declared payloads from this node's direct dependencies.

        Direct dependencies only, and payloads only. A node does not receive the whole
        history: that would grow the prompt with every step and let unrelated output
        influence the result.
        """
        upstream = []
        for edge in plan.edges:
            if edge.target != node_key or not edge.pass_payload:
                continue
            output = state.outputs.get(edge.source)
            if output is not None and output.succeeded:
                upstream.append(
                    UpstreamResult(
                        node_key=edge.source,
                        agent_id=output.agent_id,
                        payload=output.payload,
                    )
                )
        return tuple(upstream)

    @staticmethod
    def _final_result(plan: WorkflowPlan, state: WorkflowRun) -> dict[str, object]:
        return synthesise(plan, state.outputs, state.skipped, total_cost_usd=state.total_cost_usd)


def output_statuses(run: WorkflowRun) -> dict[str, ExecutionStatus]:
    """Convenience for tests and diagnostics."""
    return {key: output.status for key, output in run.outputs.items()}
