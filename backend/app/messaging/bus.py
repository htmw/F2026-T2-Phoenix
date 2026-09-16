"""The agent message bus.

Agents send structured envelopes to each other through this module. The orchestrator
is a participant (``orchestrator``), not a mandatory hop: a security agent can address
the coding agent directly, and the message is stored in both outbox and inbox without
the workflow engine copying it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentNotFoundError, AgentRegistry
from app.core.logging import get_logger
from app.domain.enums import MessagePriority, MessageStatus, MessageType, NetworkEventType
from app.models.network import AgentMessageRecord, NetworkEventRecord
from app.schemas.messaging import (
    ORCHESTRATOR_ID,
    AgentMailboxView,
    AgentMessageCreate,
    AgentMessageView,
)

logger = get_logger(__name__)

_ACTIVE_INBOX = frozenset(
    {
        MessageStatus.QUEUED,
        MessageStatus.DELIVERED,
        MessageStatus.ACKNOWLEDGED,
    }
)
_ARCHIVE_INBOX = frozenset({MessageStatus.COMPLETED, MessageStatus.FAILED})


class MessageBusError(ValueError):
    """Raised when a message cannot be accepted."""


class MessageNotFoundError(KeyError):
    pass


def _reply_type_for(parent_type: MessageType) -> MessageType:
    """Map a request envelope to the typed response the bus should emit."""
    mapping = {
        MessageType.INFORMATION_REQUEST: MessageType.INFORMATION_RESPONSE,
        MessageType.CONTEXT_REQUEST: MessageType.CONTEXT_RESPONSE,
        MessageType.DELEGATION: MessageType.TASK_RESPONSE,
        MessageType.TASK_REQUEST: MessageType.TASK_RESPONSE,
        MessageType.ARTIFACT_SHARE: MessageType.ARTIFACT_REFERENCE,
    }
    return mapping.get(parent_type, MessageType.TASK_RESPONSE)


def _view(row: AgentMessageRecord) -> AgentMessageView:
    return AgentMessageView(
        id=row.id,
        sender=row.sender_id,
        recipient=row.recipient_id,
        type=MessageType(row.type),
        priority=MessagePriority(row.priority),
        status=MessageStatus(row.status),
        workflow_id=row.workflow_id,
        task_id=row.task_id,
        node_key=row.node_key,
        parent_id=row.parent_id,
        content=row.content,
        artifact_ids=list(row.artifact_ids or []),
        requires_response=row.requires_response,
        created_at=row.created_at,
        acknowledged_at=row.acknowledged_at,
        completed_at=row.completed_at,
    )


class MessageBus:
    def __init__(self, session: AsyncSession, registry: AgentRegistry) -> None:
        self._session = session
        self._registry = registry

    async def send(self, envelope: AgentMessageCreate) -> AgentMessageView:
        await self._assert_sender(envelope.sender)
        if envelope.recipient is None:
            return await self._broadcast(envelope)
        await self._assert_recipient(envelope.recipient)
        if envelope.sender == envelope.recipient:
            raise MessageBusError("an agent cannot message itself")
        row = self._row_from(envelope, envelope.recipient, MessageStatus.DELIVERED)
        self._session.add(row)
        await self._session.flush()
        await self._record_event(row, NetworkEventType.MESSAGE_SENT)
        logger.info(
            "message_sent",
            message_id=str(row.id),
            sender=row.sender_id,
            recipient=row.recipient_id,
            type=row.type,
            workflow_id=str(row.workflow_id) if row.workflow_id else None,
        )
        return _view(row)

    async def inbox(
        self,
        agent_id: str,
        *,
        status: MessageStatus | None = None,
        statuses: frozenset[MessageStatus] | None = None,
        workflow_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[AgentMessageView]:
        await self._assert_recipient(agent_id)
        query = select(AgentMessageRecord).where(
            or_(
                AgentMessageRecord.recipient_id == agent_id,
                AgentMessageRecord.recipient_id.is_(None),
            )
        )
        if status is not None:
            query = query.where(AgentMessageRecord.status == status)
        elif statuses is not None:
            query = query.where(AgentMessageRecord.status.in_([item.value for item in statuses]))
        if workflow_id is not None:
            query = query.where(AgentMessageRecord.workflow_id == workflow_id)
        rank = case(
            (AgentMessageRecord.priority == MessagePriority.URGENT.value, 0),
            (AgentMessageRecord.priority == MessagePriority.HIGH.value, 1),
            (AgentMessageRecord.priority == MessagePriority.MEDIUM.value, 2),
            else_=3,
        )
        query = query.order_by(rank, AgentMessageRecord.created_at.desc()).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return [_view(row) for row in rows]

    async def outbox(self, agent_id: str, *, limit: int = 100) -> list[AgentMessageView]:
        await self._assert_sender(agent_id)
        rows = (
            (
                await self._session.execute(
                    select(AgentMessageRecord)
                    .where(AgentMessageRecord.sender_id == agent_id)
                    .order_by(AgentMessageRecord.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [_view(row) for row in rows]

    async def mailbox(self, agent_id: str, *, limit: int = 100) -> AgentMailboxView:
        """Active inbox, sent folder, and completed/failed archive for one agent."""
        inbox = await self.inbox(agent_id, statuses=_ACTIVE_INBOX, limit=limit)
        sent = await self.outbox(agent_id, limit=limit)
        archive = await self.inbox(agent_id, statuses=_ARCHIVE_INBOX, limit=limit)
        return AgentMailboxView(inbox=inbox, sent=sent, archive=archive)

    async def get(self, message_id: uuid.UUID) -> AgentMessageView:
        row = await self._session.get(AgentMessageRecord, message_id)
        if row is None:
            raise MessageNotFoundError(str(message_id))
        return _view(row)

    async def acknowledge(self, message_id: uuid.UUID, agent_id: str) -> AgentMessageView:
        row = await self._require(message_id)
        if row.recipient_id not in {agent_id, None}:
            raise MessageBusError("only the recipient can acknowledge a message")
        row.status = MessageStatus.ACKNOWLEDGED
        row.acknowledged_at = datetime.now(UTC)
        await self._session.flush()
        return _view(row)

    async def complete(self, message_id: uuid.UUID, agent_id: str) -> AgentMessageView:
        row = await self._require(message_id)
        if row.recipient_id not in {agent_id, None}:
            raise MessageBusError("only the recipient can complete a message")
        row.status = MessageStatus.COMPLETED
        row.completed_at = datetime.now(UTC)
        await self._session.flush()
        return _view(row)

    async def respond(
        self, parent_id: uuid.UUID, sender: str, content: dict[str, object]
    ) -> AgentMessageView:
        parent = await self._require(parent_id)
        if parent.recipient_id not in {sender, None}:
            raise MessageBusError("only the recipient can reply")
        parent_type = MessageType(parent.type)
        reply_type = _reply_type_for(parent_type)
        reply = AgentMessageCreate(
            sender=sender,
            recipient=parent.sender_id,
            type=reply_type,
            content=content,
            workflow_id=parent.workflow_id,
            task_id=parent.task_id,
            parent_id=parent.id,
            requires_response=False,
        )
        parent.status = MessageStatus.COMPLETED
        parent.completed_at = datetime.now(UTC)
        return await self.send(reply)

    async def recent(
        self, *, workflow_id: uuid.UUID | None = None, limit: int = 50
    ) -> list[AgentMessageView]:
        query = select(AgentMessageRecord)
        if workflow_id is not None:
            query = query.where(AgentMessageRecord.workflow_id == workflow_id)
        query = query.order_by(AgentMessageRecord.created_at.desc()).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return [_view(row) for row in rows]

    async def _broadcast(self, envelope: AgentMessageCreate) -> AgentMessageView:
        agents = await self._registry.list_all()
        recipients = [agent.id for agent in agents if agent.id != envelope.sender]
        if not recipients:
            raise MessageBusError("broadcast has no recipients")
        last: AgentMessageRecord | None = None
        for recipient in recipients:
            row = self._row_from(envelope, recipient, MessageStatus.DELIVERED)
            self._session.add(row)
            last = row
        await self._session.flush()
        if last is None:
            raise MessageBusError("broadcast has no recipients")
        await self._record_event(last, NetworkEventType.MESSAGE_SENT)
        logger.info(
            "message_broadcast",
            sender=envelope.sender,
            recipients=len(recipients),
            type=envelope.type.value,
        )
        return _view(last)

    def _row_from(
        self, envelope: AgentMessageCreate, recipient: str, status: MessageStatus
    ) -> AgentMessageRecord:
        return AgentMessageRecord(
            sender_id=envelope.sender,
            recipient_id=recipient,
            type=envelope.type.value,
            priority=envelope.priority.value,
            status=status.value,
            workflow_id=envelope.workflow_id,
            task_id=envelope.task_id,
            node_key=envelope.node_key,
            parent_id=envelope.parent_id,
            content=dict(envelope.content),
            artifact_ids=[str(item) for item in envelope.artifact_ids],
            requires_response=envelope.requires_response,
        )

    async def _assert_sender(self, agent_id: str) -> None:
        if agent_id == ORCHESTRATOR_ID:
            return
        try:
            await self._registry.get(agent_id)
        except AgentNotFoundError:
            raise MessageBusError(f"sender '{agent_id}' is not a registered agent") from None

    async def _assert_recipient(self, agent_id: str) -> None:
        if agent_id == ORCHESTRATOR_ID:
            return
        try:
            await self._registry.get(agent_id)
        except AgentNotFoundError:
            raise MessageBusError(f"recipient '{agent_id}' is not a registered agent") from None

    async def _require(self, message_id: uuid.UUID) -> AgentMessageRecord:
        row = await self._session.get(AgentMessageRecord, message_id)
        if row is None:
            raise MessageNotFoundError(str(message_id))
        return row

    async def _record_event(self, row: AgentMessageRecord, event_type: NetworkEventType) -> None:
        self._session.add(
            NetworkEventRecord(
                event_type=event_type.value,
                actor_id=row.sender_id,
                workflow_id=row.workflow_id,
                payload={
                    "message_id": str(row.id),
                    "recipient": row.recipient_id,
                    "type": row.type,
                },
            )
        )
