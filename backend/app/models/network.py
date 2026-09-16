"""Agent network tables: mailboxes, memory, artifacts, presence, and the event log.

These are the durable records that make agents an organisation rather than a pipeline.
Messages, memories, and artifacts survive a process restart; presence is overwritten
in place because only the latest status is useful.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, new_uuid
from app.domain.enums import (
    AgentRuntimeStatus,
    ArtifactKind,
    DecisionKind,
    MemoryVisibility,
    MessagePriority,
    MessageStatus,
    MessageType,
)


class AgentMessageRecord(Base, TimestampMixin):
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    sender_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default=MessageType.DIRECT)
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MessagePriority.MEDIUM
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=MessageStatus.DELIVERED)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    node_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    artifact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    requires_response: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_agent_messages_recipient_status", "recipient_id", "status"),
        Index("ix_agent_messages_sender", "sender_id"),
        Index("ix_agent_messages_workflow", "workflow_id"),
    )


class AgentPresenceRecord(Base):
    __tablename__ = "agent_presence"

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=AgentRuntimeStatus.IDLE)
    current_task: Mapped[str | None] = mapped_column(Text, nullable=True)
    waiting_for: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sending_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MemoryRecord(Base, TimestampMixin):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MemoryVisibility.SHARED
    )
    owner_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    __table_args__ = (
        Index("ix_memories_owner_visibility", "owner_agent_id", "visibility"),
        Index("ix_memories_workflow", "workflow_id"),
    )


class ArtifactRecord(Base, TimestampMixin):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default=ArtifactKind.FILE)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_artifacts_created_by", "created_by"),)


class DecisionRecord(Base, TimestampMixin):
    """First-class office decisions with optional retention (expires_at)."""

    __tablename__ = "decision_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default=DecisionKind.OPERATOR)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    node_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_decision_records_workflow", "workflow_id"),
        Index("ix_decision_records_agent", "agent_id"),
        Index("ix_decision_records_kind", "kind"),
        Index("ix_decision_records_expires", "expires_at"),
    )


class NetworkEventRecord(Base):
    """Append-only. Rows are never updated; that is what makes a run replayable."""

    __tablename__ = "network_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_network_events_workflow_created", "workflow_id", "created_at"),
        Index("ix_network_events_type", "event_type"),
    )
