"""Shared domain vocabulary.

These enums are referenced by database models, API schemas, and the orchestrator, so
they live in one place rather than being redefined per layer. String values are stored
verbatim in the database, so renaming a member is a migration, not a refactor.
"""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    """Units of work an agent can perform.

    The orchestrator reasons about capabilities, never about agent names: that is what
    lets a new agent become selectable without touching the engine.
    """

    TASK_DECOMPOSITION = "task.decomposition"
    GENERAL_ASSISTANCE = "task.general"
    WEB_RESEARCH = "research.web"
    SUMMARISATION = "research.summarisation"
    SOURCE_EXTRACTION = "research.source_extraction"
    CODE_GENERATION = "code.generation"
    CODE_MODIFICATION = "code.modification"
    DEBUGGING = "code.debugging"
    VULNERABILITY_ANALYSIS = "security.vulnerability_analysis"
    SECURITY_RECOMMENDATION = "security.recommendation"
    DEPENDENCY_AUDIT = "security.dependency_audit"
    TEST_GENERATION = "testing.generation"
    TEST_ANALYSIS = "testing.analysis"
    TEST_EXECUTION = "testing.execution"
    CODE_REVIEW = "review.code"
    QUALITY_ASSESSMENT = "review.quality"
    DOCUMENTATION = "documentation.authoring"
    REPORT_GENERATION = "documentation.report"


class ModelTrait(StrEnum):
    """What a model is good at, used by routing instead of hard-coded model names."""

    REASONING = "reasoning"
    CODING = "coding"
    FAST = "fast"
    CHEAP = "cheap"
    LONG_CONTEXT = "long_context"
    STRUCTURED_OUTPUT = "structured_output"


class RoutingStrategy(StrEnum):
    """How a run chooses models for its agents.

    - ``auto`` — each agent uses Fixed binding if set, otherwise the trait router
    - ``one`` — one shared catalogue model for every agent on the run
    - ``mixed`` — per-agent catalogue overrides for this run (others stay Auto/Fixed)
    """

    AUTO = "auto"
    ONE = "one"
    MIXED = "mixed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeStatus(StrEnum):
    """Lifecycle of one agent slot in a workflow graph.

    SKIPPED is a first-class success state, not an error: deciding an agent is
    unnecessary is the product's core behaviour.
    """

    WAITING = "waiting"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"


class ExecutionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INVALID_OUTPUT = "invalid_output"
    BUDGET_EXCEEDED = "budget_exceeded"


class ErrorKind(StrEnum):
    """Error taxonomy shared by every provider adapter.

    Adapters map vendor-specific failures onto these so retry policy can be written
    once instead of per provider.
    """

    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"
    CONTENT_FILTERED = "content_filtered"
    INVALID_OUTPUT = "invalid_output"
    BUDGET_EXCEEDED = "budget_exceeded"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"

    @property
    def is_retryable(self) -> bool:
        """Whether retrying the same call could plausibly succeed.

        Retrying an authentication failure or a malformed request just burns money and
        latency, so the taxonomy carries this rather than leaving it to each caller.
        """
        return self in _RETRYABLE_ERRORS


_RETRYABLE_ERRORS = frozenset(
    {
        ErrorKind.TIMEOUT,
        ErrorKind.RATE_LIMITED,
        ErrorKind.PROVIDER_UNAVAILABLE,
        ErrorKind.INVALID_OUTPUT,
        ErrorKind.UNKNOWN,
    }
)


class ProviderConnectionStatus(StrEnum):
    """Operator-facing health of a stored provider credential."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    AUTH_FAILED = "auth_failed"
    UNAVAILABLE = "unavailable"
    NO_MODELS = "no_models"


class MessageType(StrEnum):
    """Kinds of traffic the agent message bus carries."""

    DIRECT = "direct"
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    INFORMATION_REQUEST = "information_request"
    INFORMATION_RESPONSE = "information_response"
    DELEGATION = "delegation"
    CONTEXT_REQUEST = "context_request"
    CONTEXT_RESPONSE = "context_response"
    ARTIFACT_SHARE = "artifact_share"
    STATUS_UPDATE = "status_update"
    ARTIFACT_REFERENCE = "artifact_reference"
    WORKFLOW_EVENT = "workflow_event"
    ERROR = "error"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    BROADCAST = "broadcast"
    DISCOVERY = "discovery"


class MessagePriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class MessageStatus(StrEnum):
    QUEUED = "queued"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRuntimeStatus(StrEnum):
    ONLINE = "online"
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    WAITING = "waiting"
    BLOCKED = "blocked"
    FAILED = "failed"
    OFFLINE = "offline"


class MemoryVisibility(StrEnum):
    """The three knowledge scopes. Mixing them in one row is a bug."""

    PRIVATE = "private"
    SHARED = "shared"
    WORKFLOW = "workflow"


class ArtifactKind(StrEnum):
    FILE = "file"
    REPORT = "report"
    JSON = "json"
    PATCH = "patch"
    URL = "url"
    DOCUMENT = "document"
    TEST_RESULTS = "test_results"


class DecisionKind(StrEnum):
    """First-class office decisions — not just a memory tag."""

    APPROVAL = "approval"
    SELECTION = "selection"
    ROUTING = "routing"
    AGENT = "agent"
    OPERATOR = "operator"


class NetworkEventType(StrEnum):
    AGENT_CREATED = "agent_created"
    TASK_CREATED = "task_created"
    TASK_ASSIGNED = "task_assigned"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    ARTIFACT_CREATED = "artifact_created"
    DECISION_RECORDED = "decision_recorded"
    MEMORY_UPDATED = "memory_updated"
    WORKFLOW_BRANCH_CREATED = "workflow_branch_created"
    WORKFLOW_COMPLETED = "workflow_completed"
    HUMAN_APPROVAL_REQUESTED = "human_approval_requested"
