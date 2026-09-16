"""Response models for the HTTP API.

Separate from the domain contracts so the wire format can stay stable while internal
types evolve, and so nothing internal is exposed by accident.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.agents.builtin import agent_display_name
from app.domain.enums import ExecutionStatus, NodeStatus, WorkflowStatus
from app.models.workflow import WorkflowRecord
from app.schemas.execution import AgentOutput


class ExecutionSummary(BaseModel):
    attempt: int
    status: ExecutionStatus
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    error_kind: str | None
    error_message: str | None


class ApprovalView(BaseModel):
    approved: bool
    decided_by: str
    reason: str | None = None
    decided_at: str | None = None


class NodeView(BaseModel):
    key: str
    agent_id: str
    #: Original agent display name (e.g. "Security Agent"), never a stripped id.
    agent_name: str = ""
    objective: str
    status: NodeStatus
    satisfies: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    #: Populated when the node was deliberately not run; the UI shows this verbatim.
    skip_reason: str | None = None
    join_policy: str = "all"
    #: The node this one sends work back to when its verdict is negative.
    feedback_target: str | None = None
    attempts: int = 0
    result: dict[str, object] = Field(default_factory=dict)
    executions: list[ExecutionSummary] = Field(default_factory=list)
    approval: ApprovalView | None = None


class EdgeView(BaseModel):
    source: str
    target: str
    condition: dict[str, object] | None = None


class WorkflowView(BaseModel):
    """What a client needs to render a workflow and its progress."""

    id: uuid.UUID
    task_id: uuid.UUID
    status: WorkflowStatus
    request: str = ""
    owner_id: str = "operator"
    nodes: list[NodeView]
    edges: list[EdgeView] = Field(default_factory=list)
    selection: dict[str, object] = Field(default_factory=dict)
    total_cost_usd: float = 0.0
    final_result: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    #: True once a stop has been requested but before the engine has acted on it.
    cancel_requested: bool = False
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_record(
        cls, record: WorkflowRecord, *, include_executions: bool = True
    ) -> WorkflowView:
        nodes = []
        for node in sorted(record.nodes, key=lambda n: n.position):
            executions: list[ExecutionSummary] = []
            if include_executions:
                executions = [
                    ExecutionSummary(
                        attempt=execution.attempt,
                        status=ExecutionStatus(execution.status),
                        provider=execution.provider_id,
                        model=execution.model_id,
                        input_tokens=execution.input_tokens,
                        output_tokens=execution.output_tokens,
                        cost_usd=execution.cost_usd,
                        latency_ms=execution.latency_ms,
                        error_kind=execution.error_kind,
                        error_message=execution.error_message,
                    )
                    for execution in sorted(node.executions, key=lambda e: e.attempt)
                ]
            nodes.append(
                NodeView(
                    key=node.node_key,
                    agent_id=node.agent_id,
                    agent_name=agent_display_name(node.agent_id),
                    objective=node.objective,
                    status=NodeStatus(node.status),
                    satisfies=list(node.satisfies),
                    requires_approval=node.requires_approval,
                    skip_reason=node.skip_reason,
                    join_policy=node.join_policy,
                    feedback_target=(node.feedback or {}).get("target"),
                    attempts=node.attempts,
                    result=dict(node.result_payload),
                    executions=executions,
                    approval=_approval_view(node.approval),
                )
            )

        return cls(
            id=record.id,
            task_id=record.task_id,
            status=WorkflowStatus(record.status),
            request=record.task.request if record.task is not None else "",
            owner_id=record.owner_id,
            nodes=nodes,
            edges=[
                EdgeView(
                    source=edge.source_key,
                    target=edge.target_key,
                    condition=dict(edge.condition) if edge.condition else None,
                )
                for edge in record.edges
            ],
            selection=dict(record.selection),
            total_cost_usd=record.total_cost_usd,
            final_result=dict(record.final_result),
            error=record.error,
            cancel_requested=record.cancel_requested,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )


def _approval_view(payload: dict[str, object] | None) -> ApprovalView | None:
    if not payload:
        return None
    approved = payload.get("approved")
    decided_by = payload.get("decided_by")
    if not isinstance(approved, bool) or not isinstance(decided_by, str):
        return None
    reason = payload.get("reason")
    decided_at = payload.get("decided_at")
    return ApprovalView(
        approved=approved,
        decided_by=decided_by,
        reason=reason if isinstance(reason, str) else None,
        decided_at=decided_at if isinstance(decided_at, str) else None,
    )


class NodeDecision(BaseModel):
    """Optional reason for a control action.

    ``decided_by`` is ignored when an operator identity header is present — the
    authenticated operator wins so clients cannot spoof the decision log.
    """

    decided_by: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=4_000)


class OperatorLimitsView(BaseModel):
    """Live rate-limit and soft-budget status for the calling operator."""

    operator_id: str
    rate_limit: int
    rate_remaining: int
    rate_reset_at: int
    budget_cap_usd: float | None = None
    budget_spent_usd: float = 0.0
    budget_window_hours: int = 24


class AgentRunResponse(BaseModel):
    workflow: WorkflowView
    output: AgentOutput


class ModelView(BaseModel):
    id: str
    provider: str
    traits: list[str]
    context_tokens: int
    max_output_tokens: int
    input_cost_per_million: float
    output_cost_per_million: float
    #: True for development-only mock models — never present them as real AI.
    demo: bool = False
    #: True when the id was seen in the provider's live model list after refresh.
    verified: bool = False


class ProviderConnectRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


class ProviderStatusView(BaseModel):
    """Which providers are usable. Never includes credentials."""

    name: str
    #: Human label shown in Settings (e.g. "Demo Mode (development)").
    label: str
    configured: bool
    #: True when this is the isolated development mock, not a live vendor.
    demo: bool = False
    #: api_key today — only methods the integration actually supports.
    auth_method: str = "api_key"
    access_label: str = "API"
    #: connected | disconnected | auth_failed | unavailable | no_models
    connection_status: str = "disconnected"
    #: Where the active key came from: connection | env | none | demo
    credential_source: str = "none"
    key_hint: str | None = None
    last_verified_at: datetime | None = None
    last_error: str | None = None
    discovered_models: list[str] = Field(default_factory=list)
    models: list[ModelView]


class ProviderActionResult(BaseModel):
    provider: ProviderStatusView
    message: str

