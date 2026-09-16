"""Hive collaboration: drain inbox, peer consult, blackboard, and speech-act replies."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.registry import DatabaseAgentRegistry
from app.domain.enums import MemoryVisibility, MessageStatus, MessageType
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.execution import AgentInput
from app.schemas.messaging import AgentMessageCreate
from app.services import hive as hive_service
from app.services.collaboration import Collaboration
from app.services.prompting import build_system_prompt, build_user_prompt


class LiveFakeProvider(FakeProvider):
    """Same scripting as FakeProvider, but counts as a non-fake vendor for hive consult."""

    name = "openai"


@pytest.fixture
def coding_agent():
    return next(agent for agent in BUILTIN_AGENTS if agent.id == "coding-agent")


async def test_drain_inbox_acknowledges_and_formats_mail(seeded_session: AsyncSession) -> None:
    registry = DatabaseAgentRegistry(seeded_session)
    collab = Collaboration(seeded_session, registry)
    workflow_id = uuid.uuid4()

    sent = await collab.bus.send(
        AgentMessageCreate(
            sender="security-agent",
            recipient="coding-agent",
            type=MessageType.TASK_REQUEST,
            content={"summary": "Fix the injection", "act": "request"},
            workflow_id=workflow_id,
            requires_response=True,
        )
    )

    drained = await hive_service.drain_inbox(
        collab, agent_id="coding-agent", workflow_id=workflow_id
    )
    assert sent.id in drained.message_ids
    assert "Fix the injection" in drained.notes
    assert "task_request" in drained.notes

    inbox = await collab.bus.inbox(
        "coding-agent", status=MessageStatus.ACKNOWLEDGED, workflow_id=workflow_id
    )
    assert any(item.id == sent.id for item in inbox)


async def test_blackboard_is_shared_memory(seeded_session: AsyncSession) -> None:
    registry = DatabaseAgentRegistry(seeded_session)
    collab = Collaboration(seeded_session, registry)
    workflow_id = uuid.uuid4()

    await hive_service.post_blackboard(
        collab,
        agent_id="security-agent",
        workflow_id=workflow_id,
        node_key="security",
        summary="Found SQL injection",
        payload={"findings": [{"issue": "SQLi"}]},
    )
    await seeded_session.commit()

    coding_view = await collab.memory.for_agent("coding-agent", workflow_id=workflow_id)
    titles = {item.title for item in coding_view}
    assert any("Found SQL injection" in title for title in titles)
    assert any(item.visibility is MemoryVisibility.SHARED for item in coding_view)


async def test_prepare_attempt_merges_inbox_into_notes(
    seeded_session: AsyncSession, coding_agent
) -> None:
    registry = DatabaseAgentRegistry(seeded_session)
    collab = Collaboration(seeded_session, registry, providers=ProviderRegistry([FakeProvider()]))
    workflow_id = uuid.uuid4()
    task_id = uuid.uuid4()

    await collab.bus.send(
        AgentMessageCreate(
            sender="security-agent",
            recipient="coding-agent",
            type=MessageType.INFORMATION_REQUEST,
            content={"question": "Did you parameterize auth?"},
            workflow_id=workflow_id,
            requires_response=True,
        )
    )

    notes = await collab.prepare_attempt(
        agent=coding_agent,
        objective="Apply the security fix",
        peer_ids=("security-agent",),
        workflow_id=workflow_id,
        task_id=task_id,
        existing_notes="Prior board note",
    )
    assert notes is not None
    assert "Prior board note" in notes
    assert "Did you parameterize auth?" in notes
    # Fake-only registry must not burn an LLM consult call.
    assert "Peer consult answers" not in notes


async def test_consult_peers_asks_specialist_via_provider(
    seeded_session: AsyncSession, coding_agent
) -> None:
    provider = LiveFakeProvider()
    provider.queue_json(
        {
            "need_help": True,
            "requests": [
                {
                    "agent_id": "security-agent",
                    "question": "What was the highest severity finding?",
                }
            ],
            "rationale": "Need the audit detail",
        }
    )
    # Peer has no board notes yet — answer as the peer with a second call.
    provider.queue_json({"answer": "Hardcoded API key in config.py"})

    registry = DatabaseAgentRegistry(seeded_session)
    collab = Collaboration(seeded_session, registry, providers=ProviderRegistry([provider]))
    workflow_id = uuid.uuid4()
    task_id = uuid.uuid4()

    answers = await hive_service.consult_peers(
        collab,
        ProviderRegistry([provider]),
        agent=coding_agent,
        objective="Fix security findings",
        peer_ids=("security-agent",),
        workflow_id=workflow_id,
        task_id=task_id,
    )
    assert "Hardcoded API key" in answers
    assert "security-agent" in answers

    mail = await collab.bus.recent(workflow_id=workflow_id, limit=20)
    types = {item.type for item in mail}
    assert MessageType.INFORMATION_REQUEST in types
    assert MessageType.INFORMATION_RESPONSE in types


async def test_reply_to_waiting_peers_closes_requests(seeded_session: AsyncSession) -> None:
    registry = DatabaseAgentRegistry(seeded_session)
    collab = Collaboration(seeded_session, registry)
    workflow_id = uuid.uuid4()

    request = await collab.bus.send(
        AgentMessageCreate(
            sender="testing-agent",
            recipient="coding-agent",
            type=MessageType.INFORMATION_REQUEST,
            content={"question": "Is the fix ready?"},
            workflow_id=workflow_id,
            requires_response=True,
        )
    )
    await collab.bus.acknowledge(request.id, "coding-agent")

    replied = await hive_service.reply_to_waiting_peers(
        collab,
        agent_id="coding-agent",
        workflow_id=workflow_id,
        summary="Fix landed",
        payload={"changes": []},
    )
    assert replied == 1

    done = await collab.bus.inbox(
        "coding-agent", status=MessageStatus.COMPLETED, workflow_id=workflow_id
    )
    assert any(item.id == request.id for item in done)


async def test_system_prompt_teaches_hive_collaboration(coding_agent) -> None:
    prompt = build_system_prompt(coding_agent)
    assert "shared office floor" in prompt
    assert "Inbox" in prompt


async def test_user_prompt_preserves_inbox_heading(coding_agent) -> None:
    prompt = build_user_prompt(
        AgentInput(
            task_id=uuid.uuid4(),
            node_key="coding",
            agent_id="coding-agent",
            objective="Fix it",
            context_notes="# Inbox (peer mail)\n## task_request from security-agent\n{}",
        )
    )
    assert prompt.count("# Inbox") == 1
    assert "Organisational context" not in prompt


def test_provider_registry_only_fake_flag() -> None:
    assert ProviderRegistry([FakeProvider()]).only_fake is True
    assert ProviderRegistry([LiveFakeProvider()]).only_fake is False
