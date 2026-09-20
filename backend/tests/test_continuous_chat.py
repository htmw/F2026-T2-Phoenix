"""Continuous chat: a follow-up run builds on the previous turn's result.

These cover the thread linkage (``parent_workflow_id``), the context carried into the
follow-up's plan, and the endpoint that returns a whole conversation.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.providers.fake import FakeProvider

_MARKER = "SEAFOAM-MARKER-8931: the tide returns to the shore"


async def test_followup_threads_prior_result_into_its_plan(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    # First turn: a generic request lands on the general desk with a known answer.
    fake_provider.queue_json({"summary": "a short poem", "answer": _MARKER})
    first = await db_client.post(
        "/api/v1/tasks?wait=true", json={"request": "Give me a short poem about the sea."}
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert _MARKER in first_body["final_result"]["answer"]
    first_id = first_body["id"]

    # Second turn continues the first. The provider response is the default stub; what we
    # assert is that the *plan* the follow-up was given carried the prior result forward.
    second = await db_client.post(
        "/api/v1/tasks?wait=true",
        json={"request": "Make it rhyme.", "parent_workflow_id": first_id},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()

    assert second_body["parent_workflow_id"] == first_id
    objective = second_body["nodes"][0]["objective"]
    assert "Make it rhyme." in objective
    assert "Conversation so far" in objective
    assert _MARKER in objective  # the previous turn's result reached this turn


async def test_thread_endpoint_returns_the_conversation_oldest_first(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json({"summary": "one", "answer": "first turn answer"})
    first = await db_client.post(
        "/api/v1/tasks?wait=true", json={"request": "Give me a short poem about the sea."}
    )
    first_id = first.json()["id"]

    second = await db_client.post(
        "/api/v1/tasks?wait=true",
        json={"request": "Make it rhyme.", "parent_workflow_id": first_id},
    )
    second_id = second.json()["id"]

    thread = await db_client.get(f"/api/v1/workflows/{second_id}/thread")
    assert thread.status_code == 200, thread.text
    ids = [turn["id"] for turn in thread.json()]
    assert ids == [first_id, second_id]  # root first, follow-up last


async def test_unknown_parent_is_ignored_rather_than_failing(db_client: AsyncClient) -> None:
    # A follow-up pointing at a non-existent parent degrades to a fresh task: no crash,
    # no dangling link, and nothing threaded in.
    response = await db_client.post(
        "/api/v1/tasks?wait=true",
        json={"request": "Give me a short poem about the sea.", "parent_workflow_id": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parent_workflow_id"] is None
    assert "Conversation so far" not in body["nodes"][0]["objective"]
