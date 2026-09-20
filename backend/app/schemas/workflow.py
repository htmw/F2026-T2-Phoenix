"""Workflow graph contracts.

A workflow is a DAG. Sequential execution is the special case of a single path, so
nothing in these types assumes linearity.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import Capability, NodeStatus, RoutingStrategy, TaskStatus, WorkflowStatus


def _now() -> datetime:
    return datetime.now(UTC)


class TaskRequest(BaseModel):
    """What a user submits.

    Leave ``agent_ids`` empty to let capability analysis pick the roster. Provide ids to
    force exactly those agents.

    Routing:

    - ``auto`` (default) — agent Fixed bindings apply; otherwise the trait router picks
    - ``one`` — ``shared_model`` is baked onto every node
    - ``mixed`` — ``model_overrides`` pins catalogue ids per agent for this run
    """

    request: str = Field(min_length=3, max_length=20_000)
    parameters: dict[str, object] = Field(default_factory=dict)
    max_cost_usd: float | None = Field(default=None, gt=0, le=1_000)
    require_approval: bool = False
    agent_ids: list[str] | None = Field(default=None, max_length=32)
    routing_strategy: RoutingStrategy = RoutingStrategy.AUTO
    shared_model: str | None = Field(default=None, max_length=128)
    model_overrides: dict[str, str] = Field(default_factory=dict)
    #: When set, this run continues a conversation: the prior workflow's result is
    #: threaded into the new plan as context so agents build on it instead of starting
    #: over. A missing or unowned parent is ignored (the run proceeds as a fresh task).
    parent_workflow_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _validate_overrides(self) -> TaskRequest:
        if self.agent_ids is not None:
            if not self.agent_ids:
                raise ValueError("agent_ids must be non-empty when provided")
            if len(self.agent_ids) != len(set(self.agent_ids)):
                raise ValueError("agent_ids must be unique")
            for agent_id in self.agent_ids:
                if not agent_id or len(agent_id) > 64:
                    raise ValueError(f"invalid agent id: {agent_id!r}")
        for agent_id, model_id in self.model_overrides.items():
            if not agent_id or not model_id:
                raise ValueError("model_overrides keys and values must be non-empty")
            if len(agent_id) > 64 or len(model_id) > 128:
                raise ValueError("model_overrides entry is too long")

        strategy = self.routing_strategy
        # Backward compatible: overrides without an explicit strategy mean Mixed.
        # Mutate in place — returning model_copy from __init__ validators is ignored.
        if strategy == RoutingStrategy.AUTO and self.model_overrides:
            object.__setattr__(self, "routing_strategy", RoutingStrategy.MIXED)
            strategy = RoutingStrategy.MIXED

        if strategy == RoutingStrategy.ONE:
            if not self.shared_model:
                raise ValueError("shared_model is required when routing_strategy is 'one'")
            if self.model_overrides:
                raise ValueError("model_overrides cannot be set with routing_strategy 'one'")
        elif strategy == RoutingStrategy.MIXED:
            if not self.model_overrides:
                raise ValueError("model_overrides is required when routing_strategy is 'mixed'")
            if self.shared_model:
                raise ValueError("shared_model cannot be set with routing_strategy 'mixed'")
        elif strategy == RoutingStrategy.AUTO:
            if self.shared_model:
                raise ValueError("shared_model cannot be set with routing_strategy 'auto'")
        return self


class Task(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    request: str
    status: TaskStatus
    parameters: dict[str, object] = Field(default_factory=dict)
    max_cost_usd: float | None = None
    created_at: datetime = Field(default_factory=_now)


class EdgeCondition(BaseModel):
    """A condition on an edge, evaluated against the upstream agent's payload.

    Conditions are declarative data rather than expressions so they can be persisted,
    displayed in the UI, and evaluated without executing arbitrary strings.
    """

    model_config = ConfigDict(frozen=True)

    # Dotted path into the upstream payload, e.g. "findings" or "summary.severity".
    path: str = Field(min_length=1)
    operator: Literal[
        "exists",
        "not_exists",
        "is_true",
        "is_false",
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "non_empty",
        "empty",
        "contains",
    ]
    value: object = None
    description: str | None = None


class FeedbackRule(BaseModel):
    """Send this node's verdict back to an earlier node so it can try again.

    The graph stays acyclic: a rule is not an edge. It is an instruction to the engine to
    re-open a completed node, which the engine bounds with a repair-cycle limit. Encoding
    it as data means "tests failed, so the coding agent revises" is inspectable and
    testable, rather than hidden in a loop somewhere.
    """

    model_config = ConfigDict(frozen=True)

    #: Node key to re-run.
    target: str
    #: Evaluated against this node's payload; the rule fires when it holds.
    condition: EdgeCondition
    #: Dotted path to the part of the payload that explains what to fix.
    detail_path: str | None = None
    #: Prepended to the extracted detail when the target is re-run.
    message: str = "A downstream agent rejected the previous result."


class WorkflowNode(BaseModel):
    """One agent slot in the graph."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    agent_id: str
    objective: str = Field(min_length=1)
    parameters: dict[str, object] = Field(default_factory=dict)
    # Capabilities this node exists to satisfy; recorded so a selection decision can be
    # explained after the fact.
    satisfies: tuple[Capability, ...] = ()
    requires_approval: bool = False
    # "all": every incoming edge must be satisfied. "any": one is enough, which is what
    # a reporting node needs — it should still describe the branches that did run.
    join_policy: Literal["all", "any"] = "all"
    feedback: FeedbackRule | None = None
    status: NodeStatus = NodeStatus.WAITING
    skip_reason: str | None = None


class WorkflowEdge(BaseModel):
    """A dependency between two nodes, optionally conditional."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    condition: EdgeCondition | None = None
    # Whether the target should receive the source's payload as input.
    pass_payload: bool = True


class AgentSelection(BaseModel):
    """Why each agent was included or excluded.

    Persisted and returned to the client: "only the required agents ran" is a claim the
    product has to be able to evidence.
    """

    model_config = ConfigDict(frozen=True)

    required_capabilities: tuple[Capability, ...]
    selected: tuple[str, ...]
    excluded: dict[str, str] = Field(default_factory=dict)
    reasoning: str | None = None


class WorkflowPlan(BaseModel):
    """A validated graph, before persistence or execution."""

    model_config = ConfigDict(frozen=True)

    nodes: tuple[WorkflowNode, ...] = Field(min_length=1)
    edges: tuple[WorkflowEdge, ...] = ()
    selection: AgentSelection | None = None

    @model_validator(mode="after")
    def _validate_graph(self) -> WorkflowPlan:
        keys = [node.key for node in self.nodes]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            raise ValueError(f"duplicate node keys: {sorted(duplicates)}")

        known = set(keys)
        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(f"edge source '{edge.source}' is not a node")
            if edge.target not in known:
                raise ValueError(f"edge target '{edge.target}' is not a node")
            if edge.source == edge.target:
                raise ValueError(f"edge '{edge.source}' points at itself")

        if cycle := self._find_cycle():
            raise ValueError(f"workflow graph contains a cycle: {' -> '.join(cycle)}")
        return self

    def _find_cycle(self) -> list[str] | None:
        """Depth-first search for a cycle, returning the offending path if found.

        A cycle would deadlock the executor waiting on dependencies that can never be
        satisfied, so it is rejected at construction time rather than discovered at run
        time.
        """
        successors: dict[str, list[str]] = {node.key: [] for node in self.nodes}
        for edge in self.edges:
            successors[edge.source].append(edge.target)

        WHITE, GREY, BLACK = 0, 1, 2
        colour = dict.fromkeys(successors, WHITE)

        def visit(key: str, path: list[str]) -> list[str] | None:
            colour[key] = GREY
            for successor in successors[key]:
                if colour[successor] == GREY:
                    return [*path, key, successor]
                if colour[successor] == WHITE and (found := visit(successor, [*path, key])):
                    return found
            colour[key] = BLACK
            return None

        for key in successors:
            if colour[key] == WHITE and (found := visit(key, [])):
                return found
        return None

    def dependencies_of(self, node_key: str) -> tuple[str, ...]:
        return tuple(edge.source for edge in self.edges if edge.target == node_key)

    def node(self, node_key: str) -> WorkflowNode:
        for candidate in self.nodes:
            if candidate.key == node_key:
                return candidate
        raise KeyError(f"no node '{node_key}' in plan")

    def descendants_of(self, node_key: str) -> tuple[str, ...]:
        """Every node reachable from this one.

        Used when a node is re-opened for repair: everything downstream of it was
        computed from output that is about to be replaced, so it has to be recomputed
        too, or the workflow would report results derived from a superseded answer.
        """
        seen: set[str] = set()
        frontier = [node_key]
        while frontier:
            current = frontier.pop()
            for edge in self.edges:
                if edge.source == current and edge.target not in seen:
                    seen.add(edge.target)
                    frontier.append(edge.target)
        return tuple(sorted(seen))

    def roots(self) -> tuple[str, ...]:
        targets = {edge.target for edge in self.edges}
        return tuple(node.key for node in self.nodes if node.key not in targets)


class Workflow(BaseModel):
    """A persisted workflow with its current state."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    task_id: uuid.UUID
    status: WorkflowStatus
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...] = ()
    selection: AgentSelection | None = None
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Approval(BaseModel):
    """A human decision on a node that paused for approval."""

    model_config = ConfigDict(frozen=True)

    workflow_id: uuid.UUID
    node_key: str
    approved: bool
    decided_by: str
    reason: str | None = None
    decided_at: datetime = Field(default_factory=_now)
