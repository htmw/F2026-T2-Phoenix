"""Building a workflow graph from selected agents.

Edges come from what capabilities *consume*, not from a fixed pipeline. Code work
consumes research and security findings; tests and reviews consume code changes;
documentation consumes everything. Two agents that consume nothing from each other have
no edge between them and therefore run concurrently.

This is expressed over capabilities rather than agent ids, so a newly registered agent
takes its correct place in the graph — including in parallel with an existing one —
without the planner learning its name.

Stage ranks remain as the acyclicity guarantee and the tie-break for a deterministic
ordering: an edge may only run from a lower rank to a higher one, so no consumption rule
can produce a cycle.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain.enums import Capability
from app.orchestration.capability_analysis import CapabilityAnalysis
from app.orchestration.selection import SelectionResult
from app.schemas.workflow import (
    AgentSelection,
    EdgeCondition,
    FeedbackRule,
    WorkflowEdge,
    WorkflowNode,
    WorkflowPlan,
)

logger = get_logger(__name__)

# Lower rank runs earlier. Agents covering several capabilities take their earliest
# rank, because their output is what later stages consume.
_STAGE_RANKS: dict[Capability, int] = {
    Capability.TASK_DECOMPOSITION: 0,
    Capability.GENERAL_ASSISTANCE: 5,
    Capability.WEB_RESEARCH: 10,
    Capability.SUMMARISATION: 10,
    Capability.SOURCE_EXTRACTION: 10,
    Capability.DEPENDENCY_AUDIT: 20,
    Capability.VULNERABILITY_ANALYSIS: 20,
    Capability.SECURITY_RECOMMENDATION: 20,
    Capability.CODE_GENERATION: 30,
    Capability.CODE_MODIFICATION: 30,
    Capability.DEBUGGING: 30,
    Capability.TEST_GENERATION: 40,
    Capability.TEST_EXECUTION: 40,
    Capability.TEST_ANALYSIS: 40,
    Capability.CODE_REVIEW: 50,
    Capability.QUALITY_ASSESSMENT: 50,
    Capability.DOCUMENTATION: 60,
    Capability.REPORT_GENERATION: 60,
}

_DEFAULT_RANK = 35

_RESEARCH = frozenset(
    {Capability.WEB_RESEARCH, Capability.SUMMARISATION, Capability.SOURCE_EXTRACTION}
)
_SECURITY = frozenset(
    {
        Capability.VULNERABILITY_ANALYSIS,
        Capability.DEPENDENCY_AUDIT,
        Capability.SECURITY_RECOMMENDATION,
    }
)
_CODE = frozenset({Capability.CODE_GENERATION, Capability.CODE_MODIFICATION, Capability.DEBUGGING})
_TESTING = frozenset(
    {Capability.TEST_GENERATION, Capability.TEST_EXECUTION, Capability.TEST_ANALYSIS}
)
_REVIEW = frozenset({Capability.CODE_REVIEW, Capability.QUALITY_ASSESSMENT})
_PLANNING = frozenset({Capability.TASK_DECOMPOSITION})
_GENERAL = frozenset({Capability.GENERAL_ASSISTANCE})

# What each capability needs to see before it can do useful work. Anything absent from a
# consumer's set is, by construction, something it can run alongside: a security audit
# does not wait for research, and a review does not wait for tests.
_CONSUMES: dict[Capability, frozenset[Capability]] = {
    **dict.fromkeys(_PLANNING, frozenset()),
    **dict.fromkeys(_GENERAL, frozenset()),
    **dict.fromkeys(_RESEARCH, _PLANNING),
    **dict.fromkeys(_SECURITY, _PLANNING),
    **dict.fromkeys(_CODE, _PLANNING | _RESEARCH | _SECURITY),
    **dict.fromkeys(_TESTING, _PLANNING | _CODE),
    **dict.fromkeys(_REVIEW, _PLANNING | _CODE),
}

# Documentation reports on the whole run, so it consumes every other capability and is
# exempt from transitive reduction: a report assembled from only the last two branches
# would silently omit work the user paid for.
_SYNTHESIS = frozenset({Capability.DOCUMENTATION, Capability.REPORT_GENERATION})

# Conditions attached to edges, keyed by (what the source provides, what the target
# provides). Only relationships where the agents' own output schemas guarantee the field
# are encoded: a condition on a field an agent never emits would skip work permanently.
_EDGE_CONDITIONS: tuple[tuple[frozenset[Capability], frozenset[Capability], EdgeCondition], ...] = (
    (
        _SECURITY,
        _CODE,
        EdgeCondition(
            path="findings",
            operator="non_empty",
            description="the security agent reported no findings, so there is nothing to fix",
        ),
    ),
)

# Verdicts that send work back upstream. A testing agent that reports failures is the
# canonical case: the coding agent revises rather than the workflow failing.
_FEEDBACK_RULES: tuple[tuple[frozenset[Capability], frozenset[Capability], FeedbackRule], ...] = (
    (
        _TESTING,
        _CODE,
        FeedbackRule(
            target="",  # filled in with the actual upstream node key
            condition=EdgeCondition(
                path="passed",
                operator="is_false",
                description="the tests did not pass",
            ),
            detail_path="failures",
            message="The tests you were given failed. Revise the change so they pass.",
        ),
    ),
    (
        _REVIEW,
        _CODE,
        FeedbackRule(
            target="",
            condition=EdgeCondition(
                path="approved",
                operator="is_false",
                description="the review rejected the change",
            ),
            detail_path="issues",
            message="A reviewer rejected the change. Address the issues and try again.",
        ),
    ),
)


class WorkflowPlanner:
    """Produces a validated ``WorkflowPlan``.

    A node depends on another only when it consumes a capability that node provides, so
    independent agents become siblings and the engine runs them concurrently.

    ``sequential=True`` forces a single chain. It exists for the cases where ordering
    must be total — reproducing a run exactly, or isolating an interaction between two
    agents that would otherwise overlap.
    """

    def __init__(self, *, sequential: bool = False) -> None:
        self._sequential = sequential

    def plan(
        self,
        request: str,
        analysis: CapabilityAnalysis,
        selection: SelectionResult,
        *,
        require_approval: bool = False,
    ) -> WorkflowPlan:
        ordered = self._order(selection)

        drafted = tuple(
            WorkflowNode(
                key=self._node_key(agent_id),
                agent_id=agent_id,
                objective=self._objective(request, agent_id, selection),
                satisfies=tuple(sorted(selection.chosen[agent_id])),
            )
            for agent_id in ordered
        )

        # Edges are derived from the drafted nodes, then the nodes are finished with the
        # graph-dependent parts: a join policy, a verdict that routes work back, and an
        # approval gate on consequential steps when the user asked for one.
        edges = self._build_edges(drafted, selection)
        nodes = tuple(
            self._finish(node, drafted, edges, selection, require_approval=require_approval)
            for node in drafted
        )

        plan = WorkflowPlan(
            nodes=nodes,
            edges=edges,
            selection=AgentSelection(
                required_capabilities=tuple(sorted(analysis.required)),
                selected=tuple(ordered),
                excluded=selection.excluded,
                reasoning=analysis.reasoning,
            ),
        )
        logger.info(
            "workflow_planned",
            nodes=[node.key for node in plan.nodes],
            edges=[(edge.source, edge.target) for edge in plan.edges],
            conditional_edges=[(edge.source, edge.target) for edge in plan.edges if edge.condition],
            feedback=[(node.key, node.feedback.target) for node in plan.nodes if node.feedback],
            analysis_source=analysis.source,
        )
        return plan

    # ---- internals ---------------------------------------------------------

    def _order(self, selection: SelectionResult) -> tuple[str, ...]:
        def rank(agent_id: str) -> tuple[int, str]:
            # Id breaks ties so the same request always produces the same graph.
            return self._stage_of(agent_id, selection), agent_id

        return tuple(sorted(selection.chosen, key=rank))

    @staticmethod
    def _stage_of(agent_id: str, selection: SelectionResult) -> int:
        """An agent's earliest stage across the capabilities it was chosen for.

        Earliest, not latest: the agent's output is what later stages consume, so
        scheduling it late would starve them.
        """
        return min(
            (
                _STAGE_RANKS.get(capability, _DEFAULT_RANK)
                for capability in selection.chosen[agent_id]
            ),
            default=_DEFAULT_RANK,
        )

    def _build_edges(
        self, nodes: tuple[WorkflowNode, ...], selection: SelectionResult
    ) -> tuple[WorkflowEdge, ...]:
        if self._sequential:
            return tuple(
                WorkflowEdge(source=nodes[index - 1].key, target=nodes[index].key)
                for index in range(1, len(nodes))
            )

        provided = {node.key: frozenset(selection.chosen[node.agent_id]) for node in nodes}
        stage = {node.key: self._stage_of(node.agent_id, selection) for node in nodes}

        dependencies: dict[str, set[str]] = {}
        for node in nodes:
            consumed = self._consumed_by(provided[node.key])
            dependencies[node.key] = {
                other.key
                for other in nodes
                # The rank comparison is what makes a cycle impossible: two agents that
                # nominally consume each other's capabilities resolve by stage order.
                if other.key != node.key
                and stage[other.key] < stage[node.key]
                and (consumed & provided[other.key] or self._is_synthesis(provided[node.key]))
            }

        for node in nodes:
            if not self._is_synthesis(provided[node.key]):
                dependencies[node.key] = self._reduce(dependencies[node.key], dependencies)

        return tuple(
            WorkflowEdge(
                source=source,
                target=node.key,
                condition=self._condition_for(provided[source], provided[node.key]),
            )
            for node in nodes
            for source in sorted(dependencies[node.key])
        )

    @staticmethod
    def _condition_for(
        source_provides: frozenset[Capability], target_provides: frozenset[Capability]
    ) -> EdgeCondition | None:
        """The condition guarding this edge, if the capability pair has one.

        This is where "do not run the coding agent when the audit found nothing" lives:
        stated once over capabilities, so it holds for any agent that provides them.
        """
        for sources, targets, condition in _EDGE_CONDITIONS:
            if source_provides & sources and target_provides & targets:
                return condition
        return None

    def _finish(
        self,
        node: WorkflowNode,
        nodes: tuple[WorkflowNode, ...],
        edges: tuple[WorkflowEdge, ...],
        selection: SelectionResult,
        *,
        require_approval: bool = False,
    ) -> WorkflowNode:
        provided = frozenset(selection.chosen[node.agent_id])
        updates: dict[str, object] = {}

        if self._is_synthesis(provided):
            # A report should describe the branches that did run rather than vanish
            # because one of them was skipped.
            updates["join_policy"] = "any"

        if require_approval and provided & _CODE:
            # Writing or modifying code is the consequential step. Research, tests, and
            # documentation do not change the system under review, so they do not pause.
            updates["requires_approval"] = True

        upstream = {edge.source for edge in edges if edge.target == node.key}
        for sources, targets, rule in _FEEDBACK_RULES:
            if not provided & sources:
                continue
            target_key = next(
                (
                    other.key
                    for other in nodes
                    if other.key in upstream
                    and frozenset(selection.chosen[other.agent_id]) & targets
                ),
                None,
            )
            if target_key is not None:
                updates["feedback"] = rule.model_copy(update={"target": target_key})
                break

        return node.model_copy(update=updates) if updates else node

    @staticmethod
    def _consumed_by(capabilities: frozenset[Capability]) -> frozenset[Capability]:
        consumed: frozenset[Capability] = frozenset()
        for capability in capabilities:
            consumed |= _CONSUMES.get(capability, _PLANNING)
        return consumed

    @staticmethod
    def _is_synthesis(capabilities: frozenset[Capability]) -> bool:
        return bool(capabilities & _SYNTHESIS)

    @staticmethod
    def _reduce(direct: set[str], dependencies: dict[str, set[str]]) -> set[str]:
        """Drop dependencies already implied by another dependency.

        Without this, a chain also carries shortcut edges, which would hand a node
        payloads it never asked for — extra tokens, extra cost, and a graph that reads
        as more entangled than it is.
        """
        implied: set[str] = set()
        frontier = list(direct)
        while frontier:
            for ancestor in dependencies.get(frontier.pop(), set()):
                if ancestor not in implied:
                    implied.add(ancestor)
                    frontier.append(ancestor)
        return direct - implied

    @staticmethod
    def _node_key(agent_id: str) -> str:
        # Node keys are graph-local handles; deriving them from the agent id keeps a
        # workflow readable in logs and in the UI.
        return agent_id.removesuffix("-agent").replace("-", "_")

    @staticmethod
    def _objective(request: str, agent_id: str, selection: SelectionResult) -> str:
        """Give each agent the original request plus its own remit.

        Restating the user's words verbatim matters: a paraphrase drifts from what was
        actually asked, and every agent downstream inherits the drift.
        """
        capabilities = ", ".join(
            capability.value for capability in sorted(selection.chosen[agent_id])
        )
        return (
            f"{request}\n\n"
            f"Your remit for this request: {capabilities}. "
            "Address only that remit; other agents handle the rest."
        )
