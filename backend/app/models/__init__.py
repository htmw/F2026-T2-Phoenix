"""ORM models.

Importing this package registers every model on ``Base.metadata``, which is what
Alembic autogenerate and the test schema creation rely on.
"""

from app.models.agent import AgentCapabilityRecord, AgentRecord
from app.models.network import (
    AgentMessageRecord,
    AgentPresenceRecord,
    ArtifactRecord,
    DecisionRecord,
    MemoryRecord,
    NetworkEventRecord,
)
from app.models.provider import (
    ModelRecord,
    ProviderConnectionRecord,
    ProviderRecord,
    RoutingPolicyRecord,
)
from app.models.workflow import (
    AgentResultRecord,
    ExecutionRecord,
    TaskRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
    WorkflowRecord,
)

__all__ = [
    "AgentCapabilityRecord",
    "AgentMessageRecord",
    "AgentPresenceRecord",
    "AgentRecord",
    "AgentResultRecord",
    "ArtifactRecord",
    "DecisionRecord",
    "ExecutionRecord",
    "MemoryRecord",
    "ModelRecord",
    "NetworkEventRecord",
    "ProviderConnectionRecord",
    "ProviderRecord",
    "RoutingPolicyRecord",
    "TaskRecord",
    "WorkflowEdgeRecord",
    "WorkflowNodeRecord",
    "WorkflowRecord",
]
