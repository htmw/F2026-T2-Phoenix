"""Decision log, retention, and auto-captured selection/routing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.providers.fake import FAKE_MODELS


async def test_decision_log_round_trip(db_client: AsyncClient) -> None:
    created = await db_client.post(
        "/api/v1/decisions",
        json={
            "kind": "operator",
            "actor_id": "operator",
            "agent_id": "coding-agent",
            "title": "Prefer early returns",
            "summary": "Style decision for this office",
            "tags": ["style"],
            "payload": {"rule": "early_return"},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["kind"] == "operator"
    assert body["actor_id"] == "test-operator"
    assert body["expires_at"] is None

    listed = await db_client.get("/api/v1/decisions", params={"agent_id": "coding-agent"})
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json())

    detail = await db_client.get(f"/api/v1/decisions/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Prefer early returns"

    events = await db_client.get("/api/v1/events")
    assert any(
        item["event_type"] == "decision_recorded"
        and item["payload"].get("decision_id") == body["id"]
        for item in events.json()
    )


async def test_decision_retention_purge(db_client: AsyncClient) -> None:
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    expired = await db_client.post(
        "/api/v1/decisions",
        json={
            "kind": "operator",
            "actor_id": "operator",
            "title": "Temporary note",
            "expires_at": past,
        },
    )
    assert expired.status_code == 201, expired.text
    expired_id = expired.json()["id"]

    active = await db_client.get("/api/v1/decisions")
    assert not any(item["id"] == expired_id for item in active.json())

    with_expired = await db_client.get("/api/v1/decisions", params={"include_expired": True})
    assert any(item["id"] == expired_id for item in with_expired.json())

    purged = await db_client.post("/api/v1/decisions/purge-expired")
    assert purged.status_code == 200
    assert purged.json()["removed"] >= 1

    again = await db_client.get("/api/v1/decisions", params={"include_expired": True})
    assert not any(item["id"] == expired_id for item in again.json())


async def test_task_auto_captures_selection_and_routing(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/tasks?wait=true",
        json={"request": "Find security vulnerabilities in the payments service"},
    )
    assert response.status_code == 200, response.text
    workflow_id = response.json()["id"]

    decisions = await db_client.get("/api/v1/decisions", params={"workflow_id": str(workflow_id)})
    assert decisions.status_code == 200
    rows = decisions.json()
    kinds = {item["kind"] for item in rows}
    assert "selection" in kinds
    assert "routing" in kinds

    selection = next(item for item in rows if item["kind"] == "selection")
    assert selection["actor_id"] == "orchestrator"
    assert "security-agent" in selection["payload"]["selected"]

    routing = next(
        item for item in rows if item["kind"] == "routing" and item["actor_id"] == "executor"
    )
    assert routing["agent_id"] == "security-agent"
    assert routing["payload"].get("model")
    assert routing["summary"]  # routing_reason


async def test_one_model_routing_records_pin_decision(db_client: AsyncClient) -> None:
    shared = FAKE_MODELS[0].id
    response = await db_client.post(
        "/api/v1/tasks?wait=true",
        json={
            "request": "Find security vulnerabilities",
            "agent_ids": ["security-agent"],
            "routing_strategy": "one",
            "shared_model": shared,
        },
    )
    assert response.status_code == 200, response.text
    workflow_id = response.json()["id"]

    decisions = await db_client.get(
        "/api/v1/decisions",
        params={"workflow_id": str(workflow_id), "kind": "routing"},
    )
    assert decisions.status_code == 200
    pins = [
        item
        for item in decisions.json()
        if item["actor_id"] == "orchestrator" and "pin" in item.get("tags", [])
    ]
    assert pins
    assert pins[0]["payload"]["strategy"] == "one"
    assert pins[0]["payload"]["shared_model"] == shared
