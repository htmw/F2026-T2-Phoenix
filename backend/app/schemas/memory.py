"""Memory, artifact, presence, and event contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AgentRuntimeStatus,
    ArtifactKind,
    DecisionKind,
    MemoryVisibility,
    NetworkEventType,
)
from app.schemas.agent import AgentSummary
from app.schemas.messaging import AgentMessageView


class MemoryCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    visibility: MemoryVisibility
    title: str = Field(min_length=1, max_length=240)
    content: dict[str, object] = Field(default_factory=dict)
    owner_agent_id: str | None = Field(default=None, max_length=64)
    source_agent_id: str | None = Field(default=None, max_length=64)
    workflow_id: uuid.UUID | None = None
    tags: tuple[str, ...] = ()
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryView(BaseModel):
    id: uuid.UUID
    visibility: MemoryVisibility
    title: str
    content: dict[str, object]
    owner_agent_id: str | None
    source_agent_id: str | None
    workflow_id: uuid.UUID | None
    tags: list[str]
    importance: float
    created_at: datetime


class ArtifactCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ArtifactKind = ArtifactKind.FILE
    created_by: str = Field(min_length=1, max_length=64)
    uri: str = Field(min_length=1, max_length=4_000)
    title: str = Field(min_length=1, max_length=240)
    workflow_id: uuid.UUID | None = None
    content_type: str | None = None
    extra: dict[str, object] = Field(default_factory=dict)
    size_bytes: int = Field(default=0, ge=0)


class ArtifactView(BaseModel):
    """A reference, never a blob. Messages point here instead of embedding files."""

    id: uuid.UUID
    kind: ArtifactKind
    created_by: str
    uri: str
    title: str
    workflow_id: uuid.UUID | None
    content_type: str | None
    extra: dict[str, object]
    size_bytes: int
    created_at: datetime


class DecisionCreate(BaseModel):
    """Self-asserted office decision. Actor is trusted until auth lands."""

    model_config = ConfigDict(frozen=True)

    kind: DecisionKind = DecisionKind.OPERATOR
    actor_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=240)
    summary: str | None = Field(default=None, max_length=4_000)
    agent_id: str | None = Field(default=None, max_length=64)
    workflow_id: uuid.UUID | None = None
    node_key: str | None = Field(default=None, max_length=64)
    payload: dict[str, object] = Field(default_factory=dict)
    tags: tuple[str, ...] = ()
    importance: float = Field(default=0.7, ge=0.0, le=1.0)
    expires_at: datetime | None = None


class DecisionView(BaseModel):
    id: uuid.UUID
    kind: DecisionKind
    actor_id: str
    agent_id: str | None
    workflow_id: uuid.UUID | None
    node_key: str | None
    title: str
    summary: str | None
    payload: dict[str, object]
    tags: list[str]
    importance: float
    expires_at: datetime | None
    created_at: datetime


class PresenceView(BaseModel):
    agent_id: str
    status: AgentRuntimeStatus
    current_task: str | None = None
    waiting_for: str | None = None
    sending_to: str | None = None
    detail: str | None = None
    updated_at: datetime | None = None


class NetworkEventView(BaseModel):
    id: uuid.UUID
    event_type: NetworkEventType
    actor_id: str | None
    workflow_id: uuid.UUID | None
    payload: dict[str, object]
    created_at: datetime


class AgentOfficeView(BaseModel):
    """What the office UI needs for one agent: identity, live status, unread mail."""

    agent: AgentSummary
    presence: PresenceView
    inbox_unread: int = 0


class NetworkLinkView(BaseModel):
    source: str
    target: str
    type: str
    count: int
    last_at: datetime


class OfficeSnapshot(BaseModel):
    agents: list[AgentOfficeView]
    links: list[NetworkLinkView]
    recent_messages: list[AgentMessageView]
    recent_events: list[NetworkEventView]
