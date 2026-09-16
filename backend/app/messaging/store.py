"""Presence, event log, memory, artifacts, and relevant-context assembly."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.enums import (
    AgentRuntimeStatus,
    ArtifactKind,
    DecisionKind,
    MemoryVisibility,
    MessageStatus,
    NetworkEventType,
)
from app.models.network import (
    AgentMessageRecord,
    AgentPresenceRecord,
    ArtifactRecord,
    DecisionRecord,
    MemoryRecord,
    NetworkEventRecord,
)
from app.schemas.memory import (
    ArtifactCreate,
    ArtifactView,
    DecisionCreate,
    DecisionView,
    MemoryCreate,
    MemoryView,
    PresenceView,
)
from app.schemas.messaging import ContextPacket

logger = get_logger(__name__)


class PresenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set(
        self,
        agent_id: str,
        status: AgentRuntimeStatus,
        *,
        current_task: str | None = None,
        waiting_for: str | None = None,
        sending_to: str | None = None,
        detail: str | None = None,
    ) -> PresenceView:
        row = await self._session.get(AgentPresenceRecord, agent_id)
        if row is None:
            row = AgentPresenceRecord(agent_id=agent_id)
            self._session.add(row)
        row.status = status.value
        row.current_task = current_task
        row.waiting_for = waiting_for
        row.sending_to = sending_to
        row.detail = detail
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return self.view(row)

    async def get(self, agent_id: str) -> PresenceView:
        row = await self._session.get(AgentPresenceRecord, agent_id)
        if row is None:
            return PresenceView(agent_id=agent_id, status=AgentRuntimeStatus.IDLE)
        return self.view(row)

    async def all_for(self, agent_ids: list[str]) -> dict[str, PresenceView]:
        if not agent_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    select(AgentPresenceRecord).where(AgentPresenceRecord.agent_id.in_(agent_ids))
                )
            )
            .scalars()
            .all()
        )
        found = {row.agent_id: self.view(row) for row in rows}
        return {
            agent_id: found.get(
                agent_id, PresenceView(agent_id=agent_id, status=AgentRuntimeStatus.IDLE)
            )
            for agent_id in agent_ids
        }

    @staticmethod
    def view(row: AgentPresenceRecord) -> PresenceView:
        return PresenceView(
            agent_id=row.agent_id,
            status=AgentRuntimeStatus(row.status),
            current_task=row.current_task,
            waiting_for=row.waiting_for,
            sending_to=row.sending_to,
            detail=row.detail,
            updated_at=row.updated_at,
        )


class EventLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        event_type: NetworkEventType,
        *,
        actor_id: str | None = None,
        workflow_id: uuid.UUID | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        self._session.add(
            NetworkEventRecord(
                event_type=event_type.value,
                actor_id=actor_id,
                workflow_id=workflow_id,
                payload=payload or {},
            )
        )
        await self._session.flush()

    async def list(
        self, *, workflow_id: uuid.UUID | None = None, limit: int = 100
    ) -> list[NetworkEventRecord]:
        query = select(NetworkEventRecord)
        if workflow_id is not None:
            query = query.where(NetworkEventRecord.workflow_id == workflow_id)
        query = query.order_by(NetworkEventRecord.created_at.desc()).limit(limit)
        return list((await self._session.execute(query)).scalars().all())


class MemoryService:
    """Three scopes, queried separately so private notes cannot leak into a prompt."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def remember(self, entry: MemoryCreate) -> MemoryView:
        if entry.visibility is MemoryVisibility.PRIVATE and not entry.owner_agent_id:
            raise ValueError("private memory requires an owner agent")
        if entry.visibility is MemoryVisibility.WORKFLOW and entry.workflow_id is None:
            raise ValueError("workflow memory requires a workflow id")
        row = MemoryRecord(
            visibility=entry.visibility.value,
            owner_agent_id=entry.owner_agent_id,
            source_agent_id=entry.source_agent_id,
            workflow_id=entry.workflow_id,
            title=entry.title,
            content=dict(entry.content),
            tags=list(entry.tags),
            importance=entry.importance,
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "memory_written",
            memory_id=str(row.id),
            visibility=row.visibility,
            owner=row.owner_agent_id,
            workflow_id=str(row.workflow_id) if row.workflow_id else None,
        )
        return self._view(row)

    async def for_agent(
        self, agent_id: str, *, workflow_id: uuid.UUID | None = None
    ) -> list[MemoryView]:
        """Private notes for this agent, plus shared org memory, plus this workflow."""
        scopes = [
            MemoryRecord.visibility == MemoryVisibility.SHARED,
            (MemoryRecord.visibility == MemoryVisibility.PRIVATE)
            & (MemoryRecord.owner_agent_id == agent_id),
        ]
        if workflow_id is not None:
            scopes.append(
                (MemoryRecord.visibility == MemoryVisibility.WORKFLOW)
                & (MemoryRecord.workflow_id == workflow_id)
            )
        rows = (
            (
                await self._session.execute(
                    select(MemoryRecord)
                    .where(or_(*scopes))
                    .order_by(MemoryRecord.importance.desc(), MemoryRecord.created_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
        return [self._view(row) for row in rows]

    async def shared(self, *, limit: int = 50) -> list[MemoryView]:
        rows = (
            (
                await self._session.execute(
                    select(MemoryRecord)
                    .where(MemoryRecord.visibility == MemoryVisibility.SHARED)
                    .order_by(MemoryRecord.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [self._view(row) for row in rows]

    async def workflow(self, workflow_id: uuid.UUID) -> list[MemoryView]:
        rows = (
            (
                await self._session.execute(
                    select(MemoryRecord)
                    .where(
                        MemoryRecord.visibility == MemoryVisibility.WORKFLOW,
                        MemoryRecord.workflow_id == workflow_id,
                    )
                    .order_by(MemoryRecord.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [self._view(row) for row in rows]

    @staticmethod
    def _view(row: MemoryRecord) -> MemoryView:
        return MemoryView(
            id=row.id,
            visibility=MemoryVisibility(row.visibility),
            title=row.title,
            content=row.content,
            owner_agent_id=row.owner_agent_id,
            source_agent_id=row.source_agent_id,
            workflow_id=row.workflow_id,
            tags=list(row.tags or []),
            importance=row.importance,
            created_at=row.created_at,
        )


class ArtifactStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(self, artifact: ArtifactCreate) -> ArtifactView:
        row = ArtifactRecord(
            kind=artifact.kind.value,
            created_by=artifact.created_by,
            workflow_id=artifact.workflow_id,
            uri=artifact.uri,
            content_type=artifact.content_type,
            title=artifact.title,
            extra=dict(artifact.extra),
            size_bytes=artifact.size_bytes,
        )
        self._session.add(row)
        await self._session.flush()
        await EventLog(self._session).append(
            NetworkEventType.ARTIFACT_CREATED,
            actor_id=artifact.created_by,
            workflow_id=artifact.workflow_id,
            payload={
                "artifact_id": str(row.id),
                "title": artifact.title,
                "kind": artifact.kind.value,
                "uri": artifact.uri,
            },
        )
        return self._view(row)

    async def get(self, artifact_id: uuid.UUID) -> ArtifactView | None:
        row = await self._session.get(ArtifactRecord, artifact_id)
        return None if row is None else self._view(row)

    async def list(
        self,
        *,
        created_by: str | None = None,
        workflow_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[ArtifactView]:
        query = select(ArtifactRecord)
        if created_by is not None:
            query = query.where(ArtifactRecord.created_by == created_by)
        if workflow_id is not None:
            query = query.where(ArtifactRecord.workflow_id == workflow_id)
        query = query.order_by(ArtifactRecord.created_at.desc()).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return [self._view(row) for row in rows]

    @staticmethod
    def _view(row: ArtifactRecord) -> ArtifactView:
        return ArtifactView(
            id=row.id,
            kind=ArtifactKind(row.kind),
            created_by=row.created_by,
            uri=row.uri,
            title=row.title,
            workflow_id=row.workflow_id,
            content_type=row.content_type,
            extra=row.extra,
            size_bytes=row.size_bytes,
            created_at=row.created_at,
        )


class DecisionService:
    """First-class decision log with optional retention via ``expires_at``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, entry: DecisionCreate) -> DecisionView:
        row = DecisionRecord(
            kind=entry.kind.value,
            actor_id=entry.actor_id,
            agent_id=entry.agent_id,
            workflow_id=entry.workflow_id,
            node_key=entry.node_key,
            title=entry.title,
            summary=entry.summary,
            payload=dict(entry.payload),
            tags=list(entry.tags),
            importance=entry.importance,
            expires_at=entry.expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        await EventLog(self._session).append(
            NetworkEventType.DECISION_RECORDED,
            actor_id=entry.actor_id,
            workflow_id=entry.workflow_id,
            payload={
                "decision_id": str(row.id),
                "kind": entry.kind.value,
                "title": entry.title,
                "agent_id": entry.agent_id,
                "node_key": entry.node_key,
            },
        )
        return self._view(row)

    async def get(self, decision_id: uuid.UUID) -> DecisionView | None:
        row = await self._session.get(DecisionRecord, decision_id)
        return None if row is None else self._view(row)

    async def list(
        self,
        *,
        workflow_id: uuid.UUID | None = None,
        agent_id: str | None = None,
        kind: DecisionKind | None = None,
        include_expired: bool = False,
        limit: int = 50,
    ) -> list[DecisionView]:
        query = select(DecisionRecord)
        if workflow_id is not None:
            query = query.where(DecisionRecord.workflow_id == workflow_id)
        if agent_id is not None:
            query = query.where(DecisionRecord.agent_id == agent_id)
        if kind is not None:
            query = query.where(DecisionRecord.kind == kind.value)
        if not include_expired:
            now = datetime.now(UTC)
            query = query.where(
                or_(DecisionRecord.expires_at.is_(None), DecisionRecord.expires_at > now)
            )
        query = query.order_by(DecisionRecord.created_at.desc()).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return [self._view(row) for row in rows]

    async def purge_expired(self) -> int:
        """Delete decisions past ``expires_at``. Returns the number removed."""
        now = datetime.now(UTC)
        rows = (
            (
                await self._session.execute(
                    select(DecisionRecord).where(
                        DecisionRecord.expires_at.is_not(None),
                        DecisionRecord.expires_at <= now,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        return len(rows)

    @staticmethod
    def _view(row: DecisionRecord) -> DecisionView:
        return DecisionView(
            id=row.id,
            kind=DecisionKind(row.kind),
            actor_id=row.actor_id,
            agent_id=row.agent_id,
            workflow_id=row.workflow_id,
            node_key=row.node_key,
            title=row.title,
            summary=row.summary,
            payload=row.payload,
            tags=list(row.tags or []),
            importance=row.importance,
            expires_at=row.expires_at,
            created_at=row.created_at,
        )


class ContextManager:
    """Assemble a short, relevant brief for one agent attempt.

    Retrieval is metadata-first: this workflow, this agent's private notes, shared
    organisational memory, decision log entries, and recent inbox items. Full
    conversation dumps are refused.
    """

    def __init__(self, session: AsyncSession, memory: MemoryService) -> None:
        self._session = session
        self._memory = memory
        self._decisions = DecisionService(session)

    async def brief(self, agent_id: str, workflow_id: uuid.UUID | None) -> str:
        packet = await self.packet(agent_id, workflow_id)
        return packet.brief

    async def packet(
        self,
        agent_id: str,
        workflow_id: uuid.UUID | None,
        *,
        objective: str | None = None,
    ) -> ContextPacket:
        memories = await self._memory.for_agent(agent_id, workflow_id=workflow_id)
        memory_rows: list[dict[str, object]] = []
        decision_rows: list[dict[str, object]] = []
        lines: list[str] = []
        for item in memories[:8]:
            row = {
                "id": str(item.id),
                "visibility": item.visibility.value,
                "title": item.title,
                "tags": list(item.tags),
            }
            memory_rows.append(row)
            lines.append(f"- [{item.visibility.value}] {item.title}")
            if "decision" in {tag.lower() for tag in item.tags}:
                decision_rows.append(row)

        logged = await self._decisions.list(workflow_id=workflow_id, agent_id=agent_id, limit=8)
        if not logged and workflow_id is not None:
            logged = await self._decisions.list(workflow_id=workflow_id, limit=8)
        for item in logged:
            decision_rows.append(
                {
                    "id": str(item.id),
                    "kind": item.kind.value,
                    "title": item.title,
                    "actor_id": item.actor_id,
                    "source": "decision_log",
                }
            )
            lines.append(f"- [decision:{item.kind.value}] {item.title}")

        message_rows: list[dict[str, object]] = []
        if workflow_id is not None:
            messages = (
                (
                    await self._session.execute(
                        select(AgentMessageRecord)
                        .where(
                            AgentMessageRecord.recipient_id == agent_id,
                            AgentMessageRecord.workflow_id == workflow_id,
                        )
                        .order_by(AgentMessageRecord.created_at.desc())
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            for message in messages:
                summary = (
                    message.content.get("summary") or message.content.get("issue") or message.type
                )
                message_rows.append(
                    {
                        "id": str(message.id),
                        "sender": message.sender_id,
                        "type": message.type,
                        "summary": summary,
                    }
                )
                lines.append(f"- message from {message.sender_id}: {summary}")

        brief = ""
        if lines:
            brief = "Relevant context (not a full history):\n" + "\n".join(lines)
        return ContextPacket(
            agent_id=agent_id,
            workflow_id=workflow_id,
            objective=objective,
            memories=memory_rows,
            recent_messages=message_rows,
            decisions=decision_rows,
            brief=brief,
        )


async def unread_counts(session: AsyncSession, agent_ids: list[str]) -> dict[str, int]:
    if not agent_ids:
        return {}
    rows = (
        await session.execute(
            select(AgentMessageRecord.recipient_id, func.count())
            .where(
                AgentMessageRecord.recipient_id.in_(agent_ids),
                AgentMessageRecord.status.in_(
                    [MessageStatus.DELIVERED.value, MessageStatus.QUEUED.value]
                ),
            )
            .group_by(AgentMessageRecord.recipient_id)
        )
    ).all()
    found = {agent_id: int(count) for agent_id, count in rows}
    return {agent_id: found.get(agent_id, 0) for agent_id in agent_ids}
