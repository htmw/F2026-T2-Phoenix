"""Agent message bus, mailboxes, discovery, memory isolation, and artifacts."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Capability, MemoryVisibility, MessagePriority, MessageType
from app.messaging.bus import MessageBus, MessageBusError
from app.messaging.store import MemoryService
from app.providers.fake import FakeProvider
from app.schemas.memory import MemoryCreate
from app.schemas.messaging import AgentMessageCreate


async def test_direct_message_lands_in_the_recipient_inbox(
    seeded_session: AsyncSession, db_client: AsyncClient
) -> None:
    sent = await db_client.post(
        "/api/v1/messages",
        json={
            "sender": "security-agent",
            "recipient": "coding-agent",
            "type": "task_request",
            "priority": "high",
            "content": {
                "issue": "SQL injection",
                "file": "auth.js",
                "line": 143,
                "recommendation": "Use a parameterized query",
            },
            "requires_response": True,
        },
    )
    assert sent.status_code == 201
    body = sent.json()
    assert body["sender"] == "security-agent"
    assert body["recipient"] == "coding-agent"
    assert body["status"] == "delivered"

    inbox = await db_client.get("/api/v1/messages", params={"inbox": "coding-agent"})
    assert inbox.status_code == 200
    assert any(item["id"] == body["id"] for item in inbox.json())

    outbox = await db_client.get("/api/v1/messages", params={"outbox": "security-agent"})
    assert any(item["id"] == body["id"] for item in outbox.json())


async def test_unknown_sender_is_rejected(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/messages",
        json={
            "sender": "not-an-agent",
            "recipient": "coding-agent",
            "content": {"text": "hello"},
        },
    )
    assert response.status_code == 400


async def test_recipient_can_acknowledge_and_reply(db_client: AsyncClient) -> None:
    sent = await db_client.post(
        "/api/v1/messages",
        json={
            "sender": "security-agent",
            "recipient": "coding-agent",
            "type": "information_request",
            "content": {"question": "Do you have notes on authentication?"},
            "requires_response": True,
        },
    )
    message_id = sent.json()["id"]

    ack = await db_client.post(
        f"/api/v1/messages/{message_id}/acknowledge", params={"agent_id": "coding-agent"}
    )
    assert ack.json()["status"] == "acknowledged"

    reply = await db_client.post(
        f"/api/v1/messages/{message_id}/respond",
        json={"sender": "coding-agent", "content": {"answer": "Auth uses parameterized queries."}},
    )
    assert reply.status_code == 200
    assert reply.json()["recipient"] == "security-agent"
    assert reply.json()["parent_id"] == message_id
    assert reply.json()["type"] == "information_response"


async def test_mailbox_splits_inbox_sent_and_archive(db_client: AsyncClient) -> None:
    active = await db_client.post(
        "/api/v1/messages",
        json={
            "sender": "security-agent",
            "recipient": "coding-agent",
            "type": "delegation",
            "content": {"summary": "Own the auth fix", "act": "delegate"},
            "requires_response": True,
        },
    )
    assert active.status_code == 201
    active_id = active.json()["id"]

    done = await db_client.post(
        "/api/v1/messages",
        json={
            "sender": "research-agent",
            "recipient": "coding-agent",
            "type": "task_request",
            "content": {"summary": "Already handled"},
            "requires_response": True,
        },
    )
    done_id = done.json()["id"]
    await db_client.post(
        f"/api/v1/messages/{done_id}/complete", params={"agent_id": "coding-agent"}
    )

    mailbox = await db_client.get("/api/v1/agents/coding-agent/mailbox")
    assert mailbox.status_code == 200
    body = mailbox.json()
    inbox_ids = {item["id"] for item in body["inbox"]}
    archive_ids = {item["id"] for item in body["archive"]}
    assert active_id in inbox_ids
    assert active_id not in archive_ids
    assert done_id in archive_ids
    assert done_id not in inbox_ids

    sent = await db_client.get("/api/v1/agents/security-agent/mailbox")
    assert any(item["id"] == active_id for item in sent.json()["sent"])


async def test_context_request_fulfills_with_packet(db_client: AsyncClient) -> None:
    await db_client.post(
        "/api/v1/memory",
        json={
            "visibility": "shared",
            "source_agent_id": "coding-agent",
            "title": "Use early returns",
            "content": {"note": "style"},
            "tags": ["decision", "style"],
        },
    )
    sent = await db_client.post(
        "/api/v1/messages",
        json={
            "sender": "security-agent",
            "recipient": "coding-agent",
            "type": "context_request",
            "content": {"query": "coding conventions", "act": "context"},
            "requires_response": True,
        },
    )
    assert sent.status_code == 201
    message_id = sent.json()["id"]

    detail = await db_client.get(f"/api/v1/messages/{message_id}")
    assert detail.status_code == 200
    assert detail.json()["type"] == "context_request"

    fulfilled = await db_client.post(
        f"/api/v1/messages/{message_id}/fulfill-context",
        params={"agent_id": "coding-agent"},
    )
    assert fulfilled.status_code == 200
    body = fulfilled.json()
    assert body["type"] == "context_response"
    assert body["recipient"] == "security-agent"
    assert "packet" in body["content"]
    assert body["content"]["packet"]["agent_id"] == "coding-agent"
    assert any(
        item["title"] == "Use early returns" for item in body["content"]["packet"]["memories"]
    )


async def test_discovery_returns_agents_for_a_capability(db_client: AsyncClient) -> None:
    response = await db_client.get(
        "/api/v1/discovery", params={"capability": Capability.VULNERABILITY_ANALYSIS.value}
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert "security-agent" in ids
    assert "coding-agent" not in ids


async def test_private_memory_is_not_visible_to_another_agent(
    seeded_session: AsyncSession,
) -> None:
    service = MemoryService(seeded_session)
    await service.remember(
        MemoryCreate(
            visibility=MemoryVisibility.PRIVATE,
            owner_agent_id="coding-agent",
            source_agent_id="coding-agent",
            title="Prefer early returns",
            content={"note": "personal style"},
        )
    )
    await service.remember(
        MemoryCreate(
            visibility=MemoryVisibility.SHARED,
            source_agent_id="security-agent",
            title="No string-built SQL",
            content={"standard": "parameterize every query"},
            tags=("security",),
        )
    )
    await seeded_session.commit()

    coding = await service.for_agent("coding-agent")
    security = await service.for_agent("security-agent")

    coding_titles = {item.title for item in coding}
    security_titles = {item.title for item in security}
    assert "Prefer early returns" in coding_titles
    assert "Prefer early returns" not in security_titles
    assert "No string-built SQL" in coding_titles
    assert "No string-built SQL" in security_titles


async def test_artifact_is_a_reference_not_a_blob(db_client: AsyncClient) -> None:
    created = await db_client.post(
        "/api/v1/artifacts",
        json={
            "kind": "patch",
            "created_by": "coding-agent",
            "uri": "file://src/auth.js",
            "title": "auth.js parameterized query",
            "extra": {"lines": [143]},
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert "content" not in body
    assert body["uri"] == "file://src/auth.js"

    listed = await db_client.get("/api/v1/artifacts", params={"created_by": "coding-agent"})
    assert any(item["id"] == body["id"] for item in listed.json())

    detail = await db_client.get(f"/api/v1/artifacts/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "auth.js parameterized query"
    assert detail.json()["kind"] == "patch"

    missing = await db_client.get("/api/v1/artifacts/00000000-0000-0000-0000-000000000001")
    assert missing.status_code == 404

    events = await db_client.get("/api/v1/events")
    assert any(
        item["event_type"] == "artifact_created"
        and item["payload"].get("artifact_id") == body["id"]
        for item in events.json()
    )


async def test_workflow_handoff_is_a_direct_agent_message(
    seeded_session: AsyncSession, db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json(
        {
            "steps": [
                {
                    "description": "Audit for injection",
                    "capability": "security.vulnerability_analysis",
                }
            ]
        }
    )
    fake_provider.queue_json(
        {
            "findings": [
                {"severity": "high", "issue": "SQL injection", "file": "auth.js", "line": 10}
            ],
            "summary": "One injection.",
        }
    )
    fake_provider.queue_json(
        {"changes": [{"file": "auth.js", "action": "modify"}], "summary": "Parameterized."}
    )
    fake_provider.queue_json({"document": "Fixed auth.js.", "format": "markdown"})

    submitted = await db_client.post(
        "/api/v1/tasks",
        json={"request": "Find security vulnerabilities and fix them, then document the change"},
    )
    assert submitted.status_code == 200

    inbox = await db_client.get("/api/v1/messages", params={"inbox": "coding-agent"})
    types = {item["type"] for item in inbox.json()}
    senders = {item["sender"] for item in inbox.json()}
    assert "task_request" in types
    assert "security-agent" in senders

    office = await db_client.get("/api/v1/office")
    assert office.status_code == 200
    snapshot = office.json()
    assert len(snapshot["agents"]) >= 8
    assert snapshot["links"]
    assert snapshot["recent_events"]


async def test_office_lists_unread_mail(db_client: AsyncClient) -> None:
    await db_client.post(
        "/api/v1/messages",
        json={
            "sender": "planning-agent",
            "recipient": "research-agent",
            "content": {"task": "gather sources"},
        },
    )
    office = await db_client.get("/api/v1/office")
    research = next(
        item for item in office.json()["agents"] if item["agent"]["id"] == "research-agent"
    )
    assert research["inbox_unread"] >= 1


async def test_bus_rejects_self_messages(seeded_session: AsyncSession) -> None:
    from app.agents.registry import DatabaseAgentRegistry

    bus = MessageBus(seeded_session, DatabaseAgentRegistry(seeded_session))
    with pytest.raises(MessageBusError, match="cannot message itself"):
        await bus.send(
            AgentMessageCreate(
                sender="coding-agent",
                recipient="coding-agent",
                content={"text": "nope"},
            )
        )


def test_high_priority_is_an_enum_member() -> None:
    assert MessagePriority.HIGH.value == "high"
    assert MessageType.TASK_REQUEST.value == "task_request"
    assert MessageType.CONTEXT_REQUEST.value == "context_request"
    assert MessageType.DELEGATION.value == "delegation"
    assert MessageType.ARTIFACT_SHARE.value == "artifact_share"
