"""Agent network API: mailboxes, discovery, memory, artifacts, events, office snapshot.

Mutating endpoints require operator identity (``X-Operator-Id`` / Bearer). Read paths
are open so the floor can load; workflow ownership is enforced on ``/workflows``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.agents.registry import AgentNotFoundError
from app.api.dependencies import AbuseGuardDep, OperatorDep, RegistryDep, SessionDep
from app.domain.enums import Capability, DecisionKind, MessageStatus, NetworkEventType
from app.messaging.bus import MessageBus, MessageBusError, MessageNotFoundError
from app.messaging.store import (
    ArtifactStore,
    DecisionService,
    EventLog,
    MemoryService,
    PresenceService,
    unread_counts,
)
from app.models.network import AgentMessageRecord
from app.schemas.agent import AgentSummary
from app.schemas.memory import (
    AgentOfficeView,
    ArtifactCreate,
    ArtifactView,
    DecisionCreate,
    DecisionView,
    MemoryCreate,
    MemoryView,
    NetworkEventView,
    NetworkLinkView,
    OfficeSnapshot,
)
from app.schemas.messaging import (
    AgentMailboxView,
    AgentMessageCreate,
    AgentMessageView,
    MessageReply,
)
from app.services.collaboration import Collaboration

router = APIRouter(tags=["network"])


def _bus(session: SessionDep, registry: RegistryDep) -> MessageBus:
    return MessageBus(session, registry)


@router.post("/messages", response_model=AgentMessageView, status_code=status.HTTP_201_CREATED)
async def send_message(
    envelope: AgentMessageCreate, session: SessionDep, registry: RegistryDep
) -> AgentMessageView:
    try:
        return await _bus(session, registry).send(envelope)
    except MessageBusError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/messages", response_model=list[AgentMessageView])
async def list_messages(
    session: SessionDep,
    registry: RegistryDep,
    inbox: Annotated[str | None, Query(description="Agent id whose inbox to read")] = None,
    outbox: Annotated[str | None, Query()] = None,
    workflow_id: uuid.UUID | None = None,
    status_filter: Annotated[MessageStatus | None, Query(alias="status")] = None,
) -> list[AgentMessageView]:
    bus = _bus(session, registry)
    try:
        if inbox:
            return await bus.inbox(inbox, status=status_filter, workflow_id=workflow_id)
        if outbox:
            return await bus.outbox(outbox)
        return await bus.recent(workflow_id=workflow_id)
    except MessageBusError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/messages/{message_id}", response_model=AgentMessageView)
async def get_message(
    message_id: uuid.UUID, session: SessionDep, registry: RegistryDep
) -> AgentMessageView:
    try:
        return await _bus(session, registry).get(message_id)
    except MessageNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="message not found"
        ) from None


@router.post("/messages/{message_id}/acknowledge", response_model=AgentMessageView)
async def acknowledge_message(
    message_id: uuid.UUID,
    session: SessionDep,
    registry: RegistryDep,
    agent_id: Annotated[str, Query()],
) -> AgentMessageView:
    try:
        return await _bus(session, registry).acknowledge(message_id, agent_id)
    except MessageNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="message not found"
        ) from None
    except MessageBusError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.post("/messages/{message_id}/complete", response_model=AgentMessageView)
async def complete_message(
    message_id: uuid.UUID,
    session: SessionDep,
    registry: RegistryDep,
    agent_id: Annotated[str, Query()],
) -> AgentMessageView:
    try:
        return await _bus(session, registry).complete(message_id, agent_id)
    except MessageNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="message not found"
        ) from None
    except MessageBusError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.post("/messages/{message_id}/respond", response_model=AgentMessageView)
async def respond_to_message(
    message_id: uuid.UUID,
    body: MessageReply,
    session: SessionDep,
    registry: RegistryDep,
) -> AgentMessageView:
    try:
        return await _bus(session, registry).respond(message_id, body.sender, dict(body.content))
    except MessageNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="message not found"
        ) from None
    except MessageBusError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.post("/messages/{message_id}/fulfill-context", response_model=AgentMessageView)
async def fulfill_context(
    message_id: uuid.UUID,
    session: SessionDep,
    registry: RegistryDep,
    agent_id: Annotated[str, Query()],
) -> AgentMessageView:
    collab = Collaboration(session, registry)
    try:
        return await collab.fulfill_context_request(message_id=message_id, agent_id=agent_id)
    except MessageNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="message not found"
        ) from None
    except (MessageBusError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/discovery", response_model=list[AgentSummary], summary="Find agents by capability")
async def discover_agents(
    registry: RegistryDep,
    capability: Annotated[Capability, Query(description="Capability the caller needs")],
) -> list[AgentSummary]:
    definitions = await registry.find_by_capability(capability)
    return [AgentSummary.from_definition(item) for item in definitions]


@router.post("/memory", response_model=MemoryView, status_code=status.HTTP_201_CREATED)
async def write_memory(entry: MemoryCreate, session: SessionDep) -> MemoryView:
    try:
        return await MemoryService(session).remember(entry)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.get("/memory", response_model=list[MemoryView])
async def list_memory(
    session: SessionDep,
    agent_id: str | None = None,
    workflow_id: uuid.UUID | None = None,
) -> list[MemoryView]:
    service = MemoryService(session)
    if agent_id is not None:
        return await service.for_agent(agent_id, workflow_id=workflow_id)
    if workflow_id is not None:
        return await service.workflow(workflow_id)
    return await service.shared()


@router.post("/artifacts", response_model=ArtifactView, status_code=status.HTTP_201_CREATED)
async def create_artifact(body: ArtifactCreate, session: SessionDep) -> ArtifactView:
    return await ArtifactStore(session).register(body)


@router.get("/artifacts", response_model=list[ArtifactView])
async def list_artifacts(
    session: SessionDep,
    created_by: str | None = None,
    workflow_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[ArtifactView]:
    return await ArtifactStore(session).list(
        created_by=created_by, workflow_id=workflow_id, limit=limit
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactView)
async def get_artifact(artifact_id: uuid.UUID, session: SessionDep) -> ArtifactView:
    artifact = await ArtifactStore(session).get(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
    return artifact


@router.post("/decisions", response_model=DecisionView, status_code=status.HTTP_201_CREATED)
async def create_decision(
    body: DecisionCreate, session: SessionDep, operator: OperatorDep, _limits: AbuseGuardDep
) -> DecisionView:
    """Record a decision. ``actor_id`` is taken from the operator identity, not the body."""
    stamped = body.model_copy(update={"actor_id": operator.id})
    return await DecisionService(session).record(stamped)


@router.get("/decisions", response_model=list[DecisionView])
async def list_decisions(
    session: SessionDep,
    workflow_id: uuid.UUID | None = None,
    agent_id: str | None = None,
    kind: DecisionKind | None = None,
    include_expired: bool = False,
    limit: int = 50,
) -> list[DecisionView]:
    return await DecisionService(session).list(
        workflow_id=workflow_id,
        agent_id=agent_id,
        kind=kind,
        include_expired=include_expired,
        limit=limit,
    )


@router.get("/decisions/{decision_id}", response_model=DecisionView)
async def get_decision(decision_id: uuid.UUID, session: SessionDep) -> DecisionView:
    decision = await DecisionService(session).get(decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision not found")
    return decision


@router.post("/decisions/purge-expired")
async def purge_expired_decisions(session: SessionDep) -> dict[str, int]:
    removed = await DecisionService(session).purge_expired()
    return {"removed": removed}


@router.get("/events", response_model=list[NetworkEventView])
async def list_events(
    session: SessionDep, workflow_id: uuid.UUID | None = None, limit: int = 100
) -> list[NetworkEventView]:
    rows = await EventLog(session).list(workflow_id=workflow_id, limit=limit)
    return [
        NetworkEventView(
            id=row.id,
            event_type=NetworkEventType(row.event_type),
            actor_id=row.actor_id,
            workflow_id=row.workflow_id,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/office", response_model=OfficeSnapshot, summary="Agent organisation snapshot")
async def office_snapshot(session: SessionDep, registry: RegistryDep) -> OfficeSnapshot:
    agents = await registry.list_all()
    ids = [agent.id for agent in agents]
    presence = await PresenceService(session).all_for(ids)
    unread = await unread_counts(session, ids)
    office = [
        AgentOfficeView(
            agent=AgentSummary.from_definition(agent),
            presence=presence[agent.id],
            inbox_unread=unread.get(agent.id, 0),
        )
        for agent in agents
    ]
    link_rows = (
        await session.execute(
            select(
                AgentMessageRecord.sender_id,
                AgentMessageRecord.recipient_id,
                AgentMessageRecord.type,
                func.count(),
                func.max(AgentMessageRecord.created_at),
            )
            .where(AgentMessageRecord.recipient_id.is_not(None))
            .group_by(
                AgentMessageRecord.sender_id,
                AgentMessageRecord.recipient_id,
                AgentMessageRecord.type,
            )
        )
    ).all()
    links = [
        NetworkLinkView(
            source=sender,
            target=recipient,
            type=kind,
            count=int(count),
            last_at=last_at,
        )
        for sender, recipient, kind, count, last_at in link_rows
        if recipient
    ]
    recent = await _bus(session, registry).recent(limit=25)
    events = await EventLog(session).list(limit=25)
    return OfficeSnapshot(
        agents=office,
        links=links,
        recent_messages=recent,
        recent_events=[
            NetworkEventView(
                id=row.id,
                event_type=NetworkEventType(row.event_type),
                actor_id=row.actor_id,
                workflow_id=row.workflow_id,
                payload=row.payload,
                created_at=row.created_at,
            )
            for row in events
        ],
    )


@router.get("/agents/{agent_id}/inbox", response_model=list[AgentMessageView])
async def agent_inbox(
    agent_id: str, session: SessionDep, registry: RegistryDep
) -> list[AgentMessageView]:
    try:
        await registry.get(agent_id)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="agent not found"
        ) from None
    return await _bus(session, registry).inbox(agent_id)


@router.get("/agents/{agent_id}/mailbox", response_model=AgentMailboxView)
async def agent_mailbox(
    agent_id: str, session: SessionDep, registry: RegistryDep
) -> AgentMailboxView:
    try:
        await registry.get(agent_id)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="agent not found"
        ) from None
    try:
        return await _bus(session, registry).mailbox(agent_id)
    except MessageBusError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
