"""Typed envelopes for the agent message bus.

Messages are structured records, not chat turns. ``content`` is a JSON object so a
security finding or a test failure can be consumed field-by-field rather than parsed
out of prose.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import MessagePriority, MessageStatus, MessageType

ORCHESTRATOR_ID = "orchestrator"
_MAX_CONTENT_CHARS = 32_000


class AgentMessageCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    sender: str = Field(min_length=1, max_length=64)
    recipient: str | None = Field(default=None, max_length=64)
    type: MessageType = MessageType.DIRECT
    priority: MessagePriority = MessagePriority.MEDIUM
    content: dict[str, object] = Field(default_factory=dict)
    workflow_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    node_key: str | None = Field(default=None, max_length=64)
    parent_id: uuid.UUID | None = None
    artifact_ids: tuple[uuid.UUID, ...] = ()
    requires_response: bool = False

    @field_validator("content")
    @classmethod
    def _bound_content(cls, value: dict[str, object]) -> dict[str, object]:
        rendered = str(value)
        if len(rendered) > _MAX_CONTENT_CHARS:
            raise ValueError("message content exceeds the 32k character bound")
        return value


class AgentMessageView(BaseModel):
    id: uuid.UUID
    sender: str
    recipient: str | None
    type: MessageType
    priority: MessagePriority
    status: MessageStatus
    workflow_id: uuid.UUID | None
    task_id: uuid.UUID | None
    node_key: str | None
    parent_id: uuid.UUID | None
    content: dict[str, object]
    artifact_ids: list[str]
    requires_response: bool
    created_at: datetime
    acknowledged_at: datetime | None
    completed_at: datetime | None


class MessageReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    sender: str = Field(min_length=1, max_length=64)
    content: dict[str, object] = Field(default_factory=dict)
    type: MessageType = MessageType.TASK_RESPONSE
    artifact_ids: tuple[uuid.UUID, ...] = ()


class AgentMailboxView(BaseModel):
    """Per-agent folders used by the Floor desk inspector."""

    inbox: list[AgentMessageView]
    sent: list[AgentMessageView]
    archive: list[AgentMessageView]


class ContextPacket(BaseModel):
    """Relevant context for one agent — never a full conversation dump."""

    agent_id: str
    workflow_id: uuid.UUID | None = None
    objective: str | None = None
    memories: list[dict[str, object]] = Field(default_factory=list)
    recent_messages: list[dict[str, object]] = Field(default_factory=list)
    decisions: list[dict[str, object]] = Field(default_factory=list)
    brief: str = ""
