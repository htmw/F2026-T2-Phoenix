"""Workflows left running by a previous process are flagged at startup."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AgentRuntimeStatus, NodeStatus, TaskStatus, WorkflowStatus
from app.models.network import AgentPresenceRecord
from app.models.workflow import TaskRecord, WorkflowNodeRecord, WorkflowRecord
from app.services.workflow_runner import INTERRUPTED_ERROR, mark_interrupted_runs


async def _workflow(session: AsyncSession, status: WorkflowStatus) -> WorkflowRecord:
    task = TaskRecord(request="brief", status=TaskStatus.RUNNING, parameters={}, owner_id="op")
    session.add(task)
    await session.flush()
    workflow = WorkflowRecord(task_id=task.id, status=status, selection={}, owner_id="op")
    session.add(workflow)
    await session.flush()
    return workflow


async def test_stale_running_workflows_become_resumable_cancellations(
    seeded_session: AsyncSession,
) -> None:
    stale = await _workflow(seeded_session, WorkflowStatus.RUNNING)
    done = await _workflow(seeded_session, WorkflowStatus.COMPLETED)
    node = WorkflowNodeRecord(
        workflow_id=stale.id,
        node_key="main",
        agent_id="general-agent",
        objective="brief",
        parameters={},
        satisfies=[],
        status=NodeStatus.RUNNING,
        position=0,
    )
    presence = AgentPresenceRecord(agent_id="general-agent", status=AgentRuntimeStatus.WORKING)
    seeded_session.add_all([node, presence])
    await seeded_session.flush()

    assert await mark_interrupted_runs(seeded_session) == 1

    await seeded_session.refresh(stale)
    await seeded_session.refresh(done)
    await seeded_session.refresh(node)
    await seeded_session.refresh(presence)
    assert node.status == NodeStatus.CANCELLED
    assert presence.status == AgentRuntimeStatus.IDLE
    assert stale.status == WorkflowStatus.CANCELLED
    assert stale.error == INTERRUPTED_ERROR
    assert stale.completed_at is not None
    assert done.status == WorkflowStatus.COMPLETED
