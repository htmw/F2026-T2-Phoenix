"""Task, workflow graph, and execution tables.

This is the durable record that makes workflows resumable: a process can die at any
point and the graph, node states, attempts, and results are all recoverable from here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, new_uuid
from app.domain.enums import ExecutionStatus, NodeStatus, TaskStatus, WorkflowStatus


class TaskRecord(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TaskStatus.PENDING)
    parameters: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    max_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Human operator who submitted the task (JWT ``sub`` later).
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")

    workflows: Mapped[list[WorkflowRecord]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class WorkflowRecord(Base, TimestampMixin):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=WorkflowStatus.PENDING)
    # The selection record: which agents were chosen, which were excluded, and why.
    selection: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_result: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cancellation is a request, not an immediate state change: the engine is the only
    # thing allowed to decide what has actually stopped, and it may be mid-call in
    # another process when the user presses the button.
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Copied from the task so list/get can filter without a join.
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    #: Set when this workflow continues a conversation; points at the prior turn. Null
    #: for the first turn (the conversation root). SET NULL on delete so pruning an old
    #: turn never cascades away later ones.
    parent_workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[TaskRecord] = relationship(back_populates="workflows")
    nodes: Mapped[list[WorkflowNodeRecord]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan", lazy="selectin"
    )
    edges: Mapped[list[WorkflowEdgeRecord]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_workflows_status", "status"),
        Index("ix_workflows_owner_id", "owner_id"),
        Index("ix_workflows_parent", "parent_workflow_id"),
    )


class WorkflowNodeRecord(Base, TimestampMixin):
    __tablename__ = "workflow_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    # Stable, human-readable handle used by edges and the API.
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    satisfies: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=NodeStatus.WAITING)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # "all" or "any": whether every incoming edge must be satisfied for this node to run.
    join_policy: Mapped[str] = mapped_column(String(8), nullable=False, default="all")
    # Rule for returning a verdict to an earlier node (tests fail → coding revises).
    feedback: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Last human decision on this node, if any. Shape: approved, decided_by, reason,
    # decided_at. Kept on the node rather than a separate table because a node has at
    # most one outstanding gate; previous decisions remain in the audit log of attempts.
    approval: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    result_payload: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workflow: Mapped[WorkflowRecord] = relationship(back_populates="nodes")
    executions: Mapped[list[ExecutionRecord]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("workflow_id", "node_key", name="uq_workflow_nodes_node_key"),
        Index("ix_workflow_nodes_workflow_status", "workflow_id", "status"),
    )


class WorkflowEdgeRecord(Base, TimestampMixin):
    __tablename__ = "workflow_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    target_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Null means an unconditional dependency.
    condition: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    pass_payload: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    workflow: Mapped[WorkflowRecord] = relationship(back_populates="edges")

    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "source_key", "target_key", name="uq_workflow_edges_source_target"
        ),
    )


class ExecutionRecord(Base, TimestampMixin):
    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=ExecutionStatus.RUNNING)
    provider_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    node: Mapped[WorkflowNodeRecord] = relationship(back_populates="executions")
    result: Mapped[AgentResultRecord | None] = relationship(
        back_populates="execution", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("node_id", "attempt", name="uq_executions_node_attempt"),
        Index("ix_executions_status", "status"),
    )


class AgentResultRecord(Base, TimestampMixin):
    __tablename__ = "agent_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw model text is kept only when validation failed, so a bad response can be
    # debugged without storing every prompt and completion by default.
    schema_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    execution: Mapped[ExecutionRecord] = relationship(back_populates="result")
