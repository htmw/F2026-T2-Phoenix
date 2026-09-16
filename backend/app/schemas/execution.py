"""Contracts for the data agents exchange and for records of their execution.

The central rule: agents receive ``AgentInput`` containing only declared fields taken
from upstream outputs, never a conversation transcript. That keeps token cost bounded
and makes a failed hand-off inspectable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Capability, ErrorKind, ExecutionStatus


def _now() -> datetime:
    return datetime.now(UTC)


class UpstreamResult(BaseModel):
    """One upstream agent's contribution to a downstream agent's input."""

    model_config = ConfigDict(frozen=True)

    node_key: str
    agent_id: str
    payload: dict[str, object]


class AgentInput(BaseModel):
    """Everything an agent is given for one attempt."""

    model_config = ConfigDict(frozen=True)

    task_id: uuid.UUID
    node_key: str
    agent_id: str
    objective: str
    parameters: dict[str, object] = Field(default_factory=dict)
    upstream: tuple[UpstreamResult, ...] = ()
    attempt: int = Field(default=1, ge=1)
    feedback: str | None = None
    #: Relevant memory and inbox excerpts assembled by the context manager. Never a
    #: full conversation transcript.
    context_notes: str | None = None

    def upstream_payload(self, node_key: str) -> dict[str, object] | None:
        for result in self.upstream:
            if result.node_key == node_key:
                return result.payload
        return None


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class ExecutionError(BaseModel):
    """A failure, classified so retry policy can act on it without string matching."""

    model_config = ConfigDict(frozen=True)

    kind: ErrorKind
    message: str
    retryable: bool | None = None
    provider: str | None = None
    details: dict[str, object] = Field(default_factory=dict)

    @property
    def is_retryable(self) -> bool:
        # An adapter may override the taxonomy default (e.g. a 400 that is genuinely
        # transient), so an explicit flag wins when present.
        return self.kind.is_retryable if self.retryable is None else self.retryable


class AgentOutput(BaseModel):
    """What an agent produced on one attempt, after schema validation."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    node_key: str
    status: ExecutionStatus
    payload: dict[str, object] = Field(default_factory=dict)
    summary: str | None = None
    provider: str | None = None
    model: str | None = None
    #: Why the router (or Fixed pin) chose this model for the attempt.
    routing_reason: str | None = None
    #: Next eligible models after this pick (fallback order), as ``provider:model`` ids.
    routing_alternatives: tuple[str, ...] = ()
    usage: TokenUsage = TokenUsage()
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    attempt: int = Field(default=1, ge=1)
    error: ExecutionError | None = None
    # Capabilities the agent believes are still required. Advisory input to the
    # orchestrator, never a direct instruction to run something.
    suggested_capabilities: tuple[Capability, ...] = ()
    started_at: datetime = Field(default_factory=_now)
    completed_at: datetime = Field(default_factory=_now)

    @property
    def succeeded(self) -> bool:
        return self.status is ExecutionStatus.SUCCEEDED


class AgentResult(BaseModel):
    """The durable outcome for one workflow node across all of its attempts."""

    model_config = ConfigDict(frozen=True)

    node_key: str
    agent_id: str
    status: ExecutionStatus
    payload: dict[str, object] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)
    usage: TokenUsage = TokenUsage()
    cost_usd: float = Field(default=0.0, ge=0.0)
    duration_ms: float = Field(default=0.0, ge=0.0)
    error: ExecutionError | None = None
