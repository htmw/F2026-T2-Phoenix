"""Bridge between the workflow engine and the agent network.

The engine still decides *when* a node runs. This module is how agents talk: a completed
security pass becomes a ``task_request`` in the coding agent's inbox, not a payload that
only the orchestrator can see.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentRegistry
from app.domain.enums import (
    AgentRuntimeStatus,
    ArtifactKind,
    MemoryVisibility,
    MessagePriority,
    MessageType,
    NetworkEventType,
)
from app.messaging.bus import MessageBus
from app.messaging.store import (
    ArtifactStore,
    ContextManager,
    EventLog,
    MemoryService,
    PresenceService,
)
from app.providers.registry import ProviderRegistry
from app.schemas.agent import AgentDefinition
from app.schemas.execution import AgentOutput
from app.schemas.memory import ArtifactCreate, MemoryCreate
from app.schemas.messaging import ORCHESTRATOR_ID, AgentMessageCreate
from app.schemas.workflow import WorkflowPlan
from app.services import hive as hive_service
from app.services.hive import DrainedMail


class Collaboration:
    def __init__(
        self,
        session: AsyncSession,
        registry: AgentRegistry,
        providers: ProviderRegistry | None = None,
    ) -> None:
        self.bus = MessageBus(session, registry)
        self.memory = MemoryService(session)
        self.artifacts = ArtifactStore(session)
        self.presence = PresenceService(session)
        self.events = EventLog(session)
        self.context = ContextManager(session, self.memory)
        self.registry = registry
        self.providers = providers
        self._drained: dict[tuple[uuid.UUID, str], DrainedMail] = {}

    async def prepare_attempt(
        self,
        *,
        agent: AgentDefinition,
        objective: str,
        peer_ids: tuple[str, ...],
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
        existing_notes: str | None = None,
    ) -> str | None:
        """Drain inbox + optional peer consult before the main provider call."""
        notes, drained = await hive_service.prepare_hive(
            self,
            agent=agent,
            objective=objective,
            peer_ids=peer_ids,
            workflow_id=workflow_id,
            task_id=task_id,
            existing_notes=existing_notes,
        )
        self._drained[(workflow_id, agent.id)] = drained
        return notes

    async def on_node_start(
        self,
        *,
        agent_id: str,
        node_key: str,
        workflow_id: uuid.UUID,
        sending_to: str | None,
        objective: str,
    ) -> None:
        await self.presence.set(
            agent_id,
            AgentRuntimeStatus.WORKING,
            current_task=objective,
            sending_to=sending_to,
            detail=f"running {node_key}",
        )
        await self.events.append(
            NetworkEventType.AGENT_STARTED,
            actor_id=agent_id,
            workflow_id=workflow_id,
            payload={"node_key": node_key, "objective": objective},
        )

    async def on_node_finished(
        self,
        *,
        plan: WorkflowPlan,
        output: AgentOutput,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> None:
        if output.succeeded:
            await self._handoff(plan, output, workflow_id, task_id)
            drained = self._drained.pop((workflow_id, output.agent_id), None)
            if drained is not None:
                await hive_service.complete_drained_mail(
                    self, agent_id=output.agent_id, drained=drained
                )
            await self.presence.set(output.agent_id, AgentRuntimeStatus.IDLE, detail="completed")
            await self.events.append(
                NetworkEventType.AGENT_COMPLETED,
                actor_id=output.agent_id,
                workflow_id=workflow_id,
                payload={"node_key": output.node_key},
            )
            return
        self._drained.pop((workflow_id, output.agent_id), None)
        await self.presence.set(
            output.agent_id,
            AgentRuntimeStatus.FAILED,
            detail=output.error.message if output.error else "failed",
        )
        await self.bus.send(
            AgentMessageCreate(
                sender=output.agent_id,
                recipient=ORCHESTRATOR_ID,
                type=MessageType.ERROR,
                priority=MessagePriority.HIGH,
                content={
                    "node_key": output.node_key,
                    "kind": output.error.kind.value if output.error else "unknown",
                    "message": output.error.message if output.error else "failed",
                },
                workflow_id=workflow_id,
                task_id=task_id,
                node_key=output.node_key,
            )
        )
        await self.events.append(
            NetworkEventType.AGENT_FAILED,
            actor_id=output.agent_id,
            workflow_id=workflow_id,
            payload={"node_key": output.node_key},
        )

    async def on_skip(
        self, *, agent_id: str, node_key: str, workflow_id: uuid.UUID, reason: str
    ) -> None:
        await self.presence.set(agent_id, AgentRuntimeStatus.IDLE, detail=f"skipped: {reason}")
        await self.bus.send(
            AgentMessageCreate(
                sender=ORCHESTRATOR_ID,
                recipient=agent_id,
                type=MessageType.STATUS_UPDATE,
                content={"node_key": node_key, "status": "skipped", "reason": reason},
                workflow_id=workflow_id,
                node_key=node_key,
            )
        )

    async def on_feedback(
        self,
        *,
        from_agent: str,
        to_agent: str,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
        message: str,
    ) -> None:
        await self.bus.send(
            AgentMessageCreate(
                sender=from_agent,
                recipient=to_agent,
                type=MessageType.INFORMATION_REQUEST,
                priority=MessagePriority.HIGH,
                content={"summary": message, "kind": "repair", "act": "request"},
                workflow_id=workflow_id,
                task_id=task_id,
                requires_response=True,
            )
        )
        await self.presence.set(
            to_agent, AgentRuntimeStatus.WAITING, waiting_for=from_agent, detail="repair requested"
        )

    async def on_approval_requested(
        self, *, agent_id: str, node_key: str, workflow_id: uuid.UUID
    ) -> None:
        await self.presence.set(
            agent_id, AgentRuntimeStatus.WAITING, detail="human approval required"
        )
        await self.events.append(
            NetworkEventType.HUMAN_APPROVAL_REQUESTED,
            actor_id=agent_id,
            workflow_id=workflow_id,
            payload={"node_key": node_key},
        )

    async def on_workflow_completed(self, *, workflow_id: uuid.UUID) -> None:
        await self.events.append(
            NetworkEventType.WORKFLOW_COMPLETED, workflow_id=workflow_id, payload={}
        )

    async def _handoff(
        self,
        plan: WorkflowPlan,
        output: AgentOutput,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> None:
        summary = output.summary or f"{output.agent_id} completed {output.node_key}"
        await self.bus.send(
            AgentMessageCreate(
                sender=output.agent_id,
                recipient=ORCHESTRATOR_ID,
                type=MessageType.TASK_RESPONSE,
                content={
                    "summary": summary,
                    "node_key": output.node_key,
                    "payload": output.payload,
                },
                workflow_id=workflow_id,
                task_id=task_id,
                node_key=output.node_key,
            )
        )
        await self.memory.remember(
            MemoryCreate(
                visibility=MemoryVisibility.WORKFLOW,
                title=summary[:240],
                content={"payload": output.payload, "node_key": output.node_key},
                owner_agent_id=output.agent_id,
                source_agent_id=output.agent_id,
                workflow_id=workflow_id,
                tags=(output.agent_id, output.node_key),
                importance=0.7,
            )
        )
        await hive_service.post_blackboard(
            self,
            agent_id=output.agent_id,
            workflow_id=workflow_id,
            node_key=output.node_key,
            summary=summary,
            payload=output.payload,
        )
        await hive_service.reply_to_waiting_peers(
            self,
            agent_id=output.agent_id,
            workflow_id=workflow_id,
            summary=summary,
            payload=output.payload,
        )
        artifact = await self.artifacts.register(
            ArtifactCreate(
                kind=ArtifactKind.JSON,
                created_by=output.agent_id,
                uri=f"workflow://{workflow_id}/nodes/{output.node_key}",
                title=f"{output.agent_id} result",
                workflow_id=workflow_id,
                extra={"node_key": output.node_key},
            )
        )
        for edge in plan.edges:
            if edge.source != output.node_key or not edge.pass_payload:
                continue
            target = plan.node(edge.target)
            await self.bus.send(
                AgentMessageCreate(
                    sender=output.agent_id,
                    recipient=target.agent_id,
                    type=MessageType.TASK_REQUEST,
                    priority=MessagePriority.HIGH,
                    content={
                        "summary": summary,
                        "payload": output.payload,
                        "from_node": output.node_key,
                        "act": "request",
                    },
                    workflow_id=workflow_id,
                    task_id=task_id,
                    node_key=edge.target,
                    artifact_ids=(artifact.id,),
                    requires_response=True,
                )
            )
            await self.bus.send(
                AgentMessageCreate(
                    sender=output.agent_id,
                    recipient=target.agent_id,
                    type=MessageType.ARTIFACT_SHARE,
                    priority=MessagePriority.MEDIUM,
                    content={
                        "summary": f"Artifact from {output.node_key}",
                        "from_node": output.node_key,
                        "act": "share",
                    },
                    workflow_id=workflow_id,
                    task_id=task_id,
                    node_key=edge.target,
                    artifact_ids=(artifact.id,),
                )
            )

    async def request_context(
        self,
        *,
        from_agent: str,
        to_agent: str,
        workflow_id: uuid.UUID | None,
        query: str,
        task_id: uuid.UUID | None = None,
    ):
        """Ask a peer for a relevant context packet (not a full history dump)."""
        return await self.bus.send(
            AgentMessageCreate(
                sender=from_agent,
                recipient=to_agent,
                type=MessageType.CONTEXT_REQUEST,
                priority=MessagePriority.HIGH,
                content={"query": query, "act": "context"},
                workflow_id=workflow_id,
                task_id=task_id,
                requires_response=True,
            )
        )

    async def fulfill_context_request(
        self,
        *,
        message_id: uuid.UUID,
        agent_id: str,
        objective: str | None = None,
    ):
        """Answer a context_request with a ContextManager packet."""
        parent = await self.bus.get(message_id)
        if parent.type is not MessageType.CONTEXT_REQUEST:
            raise ValueError("message is not a context_request")
        if parent.recipient not in {agent_id, None}:
            raise ValueError("only the recipient can fulfill a context request")
        query = str(parent.content.get("query") or "")
        packet = await self.context.packet(
            agent_id,
            parent.workflow_id,
            objective=objective or query or None,
        )
        return await self.bus.respond(
            message_id,
            agent_id,
            {
                "query": query,
                "packet": packet.model_dump(mode="json"),
                "brief": packet.brief,
                "act": "context_response",
            },
        )

    async def delegate(
        self,
        *,
        from_agent: str,
        to_agent: str,
        workflow_id: uuid.UUID | None,
        summary: str,
        payload: dict[str, object] | None = None,
        task_id: uuid.UUID | None = None,
        artifact_ids: tuple[uuid.UUID, ...] = (),
    ):
        """Hand a sub-task to another agent via a typed delegation envelope."""
        return await self.bus.send(
            AgentMessageCreate(
                sender=from_agent,
                recipient=to_agent,
                type=MessageType.DELEGATION,
                priority=MessagePriority.HIGH,
                content={
                    "summary": summary,
                    "payload": payload or {},
                    "act": "delegate",
                },
                workflow_id=workflow_id,
                task_id=task_id,
                artifact_ids=artifact_ids,
                requires_response=True,
            )
        )
