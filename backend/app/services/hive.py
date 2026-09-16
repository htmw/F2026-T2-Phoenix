"""Hive-style agent collaboration on top of the durable message bus.

Inspired by Munder Difflin's outbox→router→inbox loop, adapted to our Postgres bus and
DAG engine: agents drain mail before they work, may consult peers (real provider calls
when keys are configured), and post results to a shared workflow blackboard.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.domain.enums import (
    AgentRuntimeStatus,
    MemoryVisibility,
    MessagePriority,
    MessageStatus,
    MessageType,
)
from app.providers.base import CompletionRequest, LLMProvider, ModelSpec
from app.providers.registry import NoSuitableModelError, ProviderRegistry
from app.schemas.agent import AgentDefinition, ModelPreference
from app.schemas.memory import MemoryCreate
from app.schemas.messaging import AgentMessageCreate, AgentMessageView

if TYPE_CHECKING:
    from app.services.collaboration import Collaboration

logger = get_logger(__name__)

_CONSULT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["need_help"],
    "additionalProperties": False,
    "properties": {
        "need_help": {"type": "boolean"},
        "requests": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["agent_id", "question"],
                "properties": {
                    "agent_id": {"type": "string"},
                    "question": {"type": "string"},
                },
            },
        },
        "rationale": {"type": "string"},
    },
}


@dataclass(slots=True)
class DrainedMail:
    """Inbox items acknowledged for this attempt, ready to mark complete afterward."""

    notes: str
    message_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass(slots=True)
class HiveContext:
    """Per-attempt collaboration state carried into the executor."""

    workflow_id: uuid.UUID
    task_id: uuid.UUID
    peer_ids: tuple[str, ...]
    drained: DrainedMail = field(default_factory=lambda: DrainedMail(notes=""))


async def drain_inbox(
    collaboration: Collaboration,
    *,
    agent_id: str,
    workflow_id: uuid.UUID,
) -> DrainedMail:
    """Acknowledge delivered mail and fold its content into the agent's brief.

    This is the hive "Stop hook drains inbox" idea: work does not start until unread
    envelopes for this workflow are read.
    """
    messages = await collaboration.bus.inbox(
        agent_id,
        status=MessageStatus.DELIVERED,
        workflow_id=workflow_id,
        limit=20,
    )
    if not messages:
        return DrainedMail(notes="")

    lines: list[str] = ["# Inbox (peer mail for this workflow)"]
    ids: list[uuid.UUID] = []
    for message in messages:
        await collaboration.bus.acknowledge(message.id, agent_id)
        ids.append(message.id)
        lines.append(_format_envelope(message))

    await collaboration.presence.set(
        agent_id,
        AgentRuntimeStatus.THINKING,
        detail=f"drained {len(ids)} inbox message(s)",
    )
    return DrainedMail(notes="\n".join(lines), message_ids=ids)


async def complete_drained_mail(
    collaboration: Collaboration, *, agent_id: str, drained: DrainedMail
) -> None:
    for message_id in drained.message_ids:
        try:
            await collaboration.bus.complete(message_id, agent_id)
        except Exception:  # noqa: BLE001 — mail lifecycle must not fail the workflow
            logger.warning("inbox_complete_failed", message_id=str(message_id), agent_id=agent_id)


async def consult_peers(
    collaboration: Collaboration,
    providers: ProviderRegistry,
    *,
    agent: AgentDefinition,
    objective: str,
    peer_ids: tuple[str, ...],
    workflow_id: uuid.UUID,
    task_id: uuid.UUID,
) -> str:
    """Optional peer consult before the main attempt.

    Uses a structured call (real provider when configured) to decide whether to ask
    specialists on the floor. Answers come from the blackboard first, then a short
    real model call as that peer when needed.
    """
    if not peer_ids:
        return ""
    # Scripted fake-only registries power hermetic tests; skip the consult LLM so queued
    # agent responses are not stolen. Real (or non-fake) providers enable mid-task asks.
    if providers.only_fake:
        return ""

    try:
        provider, model = providers.select_model(
            ModelPreference(
                preferred_traits=(),
                preferred_model=agent.model_preference.preferred_model,
                preferred_provider=agent.model_preference.preferred_provider,
                min_context_tokens=1_000,
                max_output_tokens=512,
                temperature=0.0,
            )
        )
    except NoSuitableModelError:
        return ""

    roster = ", ".join(peer_ids)
    prompt = (
        f"You are {agent.name} ({agent.id}). Before doing your main work, decide whether "
        f"you need information from another specialist already on this workflow.\n"
        f"Peers available: {roster}\n"
        f"Objective: {objective}\n"
        "If you can proceed from upstream results and inbox alone, set need_help false.\n"
        "Otherwise list at most three concrete questions for specific peer agent ids."
    )
    decision = await _json_completion(provider, model, prompt, _CONSULT_SCHEMA)
    if not decision.get("need_help"):
        return ""

    requests = decision.get("requests")
    if not isinstance(requests, list) or not requests:
        return ""

    answer_lines: list[str] = ["# Peer consult answers"]
    for item in requests[:3]:
        if not isinstance(item, dict):
            continue
        peer_id = item.get("agent_id")
        question = item.get("question")
        if not isinstance(peer_id, str) or not isinstance(question, str):
            continue
        if peer_id not in peer_ids:
            continue
        answer = await _answer_as_peer(
            collaboration,
            providers,
            peer_id=peer_id,
            question=question,
            workflow_id=workflow_id,
            asker_id=agent.id,
            task_id=task_id,
        )
        if answer:
            answer_lines.append(f"## From {peer_id}\nQ: {question}\nA: {answer}")

    if len(answer_lines) == 1:
        return ""
    return "\n".join(answer_lines)


async def prepare_hive(
    collaboration: Collaboration,
    *,
    agent: AgentDefinition,
    objective: str,
    peer_ids: tuple[str, ...],
    workflow_id: uuid.UUID,
    task_id: uuid.UUID,
    existing_notes: str | None = None,
) -> tuple[str | None, DrainedMail]:
    """Drain inbox and optionally consult peers; return merged notes + drained mail."""
    drained = await drain_inbox(collaboration, agent_id=agent.id, workflow_id=workflow_id)
    consult = ""
    if collaboration.providers is not None and peer_ids:
        consult = await consult_peers(
            collaboration,
            collaboration.providers,
            agent=agent,
            objective=objective,
            peer_ids=peer_ids,
            workflow_id=workflow_id,
            task_id=task_id,
        )
    notes = merge_notes(existing_notes, drained.notes, consult)
    return notes, drained


async def post_blackboard(
    collaboration: Collaboration,
    *,
    agent_id: str,
    workflow_id: uuid.UUID,
    node_key: str,
    summary: str,
    payload: dict[str, object],
) -> None:
    """Write a shared board note so later agents can stigmergically read results."""
    await collaboration.memory.remember(
        MemoryCreate(
            visibility=MemoryVisibility.SHARED,
            title=f"[{agent_id}] {summary[:200]}",
            content={"node_key": node_key, "payload": payload, "summary": summary},
            owner_agent_id=agent_id,
            source_agent_id=agent_id,
            workflow_id=workflow_id,
            tags=("blackboard", agent_id, node_key),
            importance=0.85,
        )
    )


async def reply_to_waiting_peers(
    collaboration: Collaboration,
    *,
    agent_id: str,
    workflow_id: uuid.UUID,
    summary: str,
    payload: dict[str, object],
) -> int:
    """Close out information/task requests still waiting on this agent."""
    pending = await collaboration.bus.inbox(
        agent_id, status=MessageStatus.ACKNOWLEDGED, workflow_id=workflow_id, limit=20
    )
    delivered = await collaboration.bus.inbox(
        agent_id, status=MessageStatus.DELIVERED, workflow_id=workflow_id, limit=20
    )
    replied = 0
    for message in [*pending, *delivered]:
        if not message.requires_response:
            continue
        if message.type not in {
            MessageType.INFORMATION_REQUEST,
            MessageType.TASK_REQUEST,
            MessageType.CONTEXT_REQUEST,
            MessageType.DELEGATION,
        }:
            continue
        await collaboration.bus.respond(
            message.id,
            agent_id,
            {"summary": summary, "payload": payload, "in_reply_to": str(message.id)},
        )
        replied += 1
    return replied


def merge_notes(*parts: str | None) -> str | None:
    chunks = [part.strip() for part in parts if part and part.strip()]
    return "\n\n".join(chunks) if chunks else None


def peer_ids_on_floor(plan_agent_ids: tuple[str, ...], current_agent_id: str) -> tuple[str, ...]:
    return tuple(aid for aid in plan_agent_ids if aid != current_agent_id)


def _format_envelope(message: AgentMessageView) -> str:
    body = json.dumps(message.content, indent=2, sort_keys=True, default=str)
    if len(body) > 4_000:
        body = body[:4_000] + "\n... [truncated]"
    return (
        f"## {message.type.value} from {message.sender} (priority={message.priority.value})\n{body}"
    )


async def _answer_as_peer(
    collaboration: Collaboration,
    providers: ProviderRegistry,
    *,
    peer_id: str,
    question: str,
    workflow_id: uuid.UUID,
    asker_id: str,
    task_id: uuid.UUID,
) -> str:
    request_msg = await collaboration.bus.send(
        AgentMessageCreate(
            sender=asker_id,
            recipient=peer_id,
            type=MessageType.INFORMATION_REQUEST,
            priority=MessagePriority.HIGH,
            content={"question": question, "act": "query"},
            workflow_id=workflow_id,
            task_id=task_id,
            requires_response=True,
        )
    )

    board = await collaboration.memory.for_agent(peer_id, workflow_id=workflow_id)
    board_bits = [
        f"{item.title}: {json.dumps(item.content, default=str)[:800]}"
        for item in board[:5]
        if item.source_agent_id == peer_id or peer_id in item.tags
    ]
    if not board_bits:
        board_bits = [
            f"{item.title}: {json.dumps(item.content, default=str)[:800]}" for item in board[:5]
        ]

    answer = ""
    if board_bits:
        answer = "From the shared board:\n- " + "\n- ".join(board_bits)
    else:
        try:
            peer = await collaboration.registry.get(peer_id)
            provider, model = providers.select_model(peer.model_preference)
            raw = await _json_completion(
                provider,
                model,
                (
                    f"You are {peer.name}. Answer this question from a teammate briefly in JSON "
                    f'{{"answer": "..."}}.\nQuestion: {question}'
                ),
                {
                    "type": "object",
                    "required": ["answer"],
                    "properties": {"answer": {"type": "string"}},
                },
            )
            maybe = raw.get("answer")
            answer = maybe if isinstance(maybe, str) else str(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("peer_answer_failed", peer_id=peer_id, error=str(exc))
            answer = "No prior board notes and peer consult failed."

    await collaboration.bus.respond(
        request_msg.id,
        peer_id,
        {"summary": answer, "act": "inform", "answer": answer},
    )
    return answer


async def _json_completion(
    provider: LLMProvider,
    model: ModelSpec,
    user_prompt: str,
    schema: dict[str, object],
) -> dict[str, object]:
    response = await provider.generate(
        CompletionRequest(
            model=model,
            system_prompt=(
                "Respond with a single JSON object only, matching the requested schema."
            ),
            user_prompt=user_prompt + "\n\nSchema:\n" + json.dumps(schema),
            max_output_tokens=min(512, model.max_output_tokens),
            temperature=0.0,
            response_schema=schema,
            timeout_seconds=45.0,
        )
    )
    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
