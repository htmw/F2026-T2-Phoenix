"""Sprint 1 application test cases (TC_01-TC_19) from the user stories document.

Each test is named after the test case it implements, so the document's "Status"
column can be filled in straight from a test run. TC_20-TC_23 are UI cases and live in
``frontend/e2e/sprint1.spec.ts``.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.tables import AGENT_DATA_SCHEMA, ensure_agent_table, table_name_for
from app.domain.enums import ExecutionStatus, NodeStatus, WorkflowStatus
from app.models.workflow import AgentResultRecord
from app.providers.fake import FakeProvider

SCORE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["summary", "score"],
    "properties": {
        "summary": {"type": "string"},
        "score": {"type": "number"},
        "passed": {"type": "boolean"},
        "attempt_count": {"type": "integer"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
}


def enrollment(name: str = "Essay Scorer", **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": name,
        "description": "Scores an essay from 0 to 10 and lists its issues.",
        "capabilities": ["review.quality"],
        "supported_models": ["groq:openai/gpt-oss-20b"],
        "input_schema": {"type": "object", "properties": {"essay": {"type": "string"}}},
        "output_schema": SCORE_SCHEMA,
        "cost_profile": {"max_cost_usd": 0.2, "timeout_seconds": 60},
    }
    body.update(overrides)
    return body


async def enroll(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/agents", json=enrollment(**overrides))
    assert response.status_code == 201, response.text
    return dict(response.json())


async def all_agents(client: AsyncClient) -> list[dict[str, Any]]:
    response = await client.get("/api/v1/agents", params={"include_disabled": "true"})
    assert response.status_code == 200
    return list(response.json())


async def column_types(
    session_factory: async_sessionmaker[AsyncSession], table: str
) -> dict[str, str]:
    async with session_factory() as session:
        rows = await session.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": AGENT_DATA_SCHEMA, "table": table},
        )
        return {row.column_name: row.data_type for row in rows}


class LogRecorder:
    """Stands in for a structlog logger and keeps every event with its bound fields."""

    def __init__(self, bound: dict[str, object] | None = None, sink: list[Any] | None = None):
        self._bound = bound or {}
        self.events: list[tuple[str, dict[str, object]]] = sink if sink is not None else []

    def bind(self, **fields: object) -> LogRecorder:
        return LogRecorder({**self._bound, **fields}, self.events)

    def __getattr__(self, _level: str) -> Any:
        def record(event: str, **fields: object) -> None:
            self.events.append((event, {**self._bound, **fields}))

        return record


async def wait_for_run(client: AsyncClient, workflow_id: str) -> None:
    runner = client._transport.app.state.workflow_runner  # type: ignore[attr-defined]
    assert await runner.wait_for(uuid.UUID(workflow_id), seconds=30)


# ---------------------------------------------------------------------------
# US_01 Agent enrollment
# ---------------------------------------------------------------------------


async def test_tc01_enroll_agent_with_valid_details(db_client: AsyncClient) -> None:
    agent = await enroll(db_client)

    assert re.fullmatch(r"essay-scorer-[0-9a-f]{8}", agent["id"])
    assert agent["status"] == "active"
    assert agent["enabled"] is True
    assert agent["capabilities"] == ["review.quality"]
    assert agent["supported_models"] == ["groq:openai/gpt-oss-20b"]
    assert agent["max_cost_usd"] == 0.2
    assert agent["timeout_seconds"] == 60

    listed = {item["id"]: item for item in (await db_client.get("/api/v1/agents")).json()}
    assert listed[agent["id"]]["status"] == "active"
    # Discoverable by capability, which is how the orchestrator finds it.
    by_capability = await db_client.get("/api/v1/agents", params={"capability": "review.quality"})
    assert agent["id"] in {item["id"] for item in by_capability.json()}


async def test_tc02_enroll_with_missing_required_field(db_client: AsyncClient) -> None:
    body = enrollment(name="No Capabilities")
    del body["capabilities"]

    response = await db_client.post("/api/v1/agents", json=body)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(error["loc"] == ["body", "capabilities"] for error in errors)
    assert "No Capabilities" not in {agent["name"] for agent in await all_agents(db_client)}


async def test_tc02_empty_capability_list_is_rejected(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/agents", json=enrollment(name="Empty Caps", capabilities=[])
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "capabilities"]


async def test_tc03_enroll_duplicate_agent_name(db_client: AsyncClient) -> None:
    original = await enroll(db_client, name="Report Grader")

    response = await db_client.post(
        "/api/v1/agents",
        json=enrollment(name="report grader", description="A different description."),
    )

    assert response.status_code == 409
    assert "already enrolled" in response.json()["detail"]
    assert response.json()["detail"].startswith("name:")
    unchanged = (await db_client.get(f"/api/v1/agents/{original['id']}")).json()
    assert unchanged["description"] == original["description"]
    names = [agent["name"].lower() for agent in await all_agents(db_client)]
    assert names.count("report grader") == 1


async def test_tc03_builtin_names_are_also_protected(db_client: AsyncClient) -> None:
    response = await db_client.post("/api/v1/agents", json=enrollment(name="Security Agent"))

    assert response.status_code == 409


async def test_tc04_enrollment_is_a_single_fast_request(db_client: AsyncClient) -> None:
    ids: list[str] = []
    for index in range(10):
        started = time.perf_counter()
        response = await db_client.post(
            "/api/v1/agents", json=enrollment(name=f"Speed Agent {index}")
        )
        elapsed = time.perf_counter() - started
        assert response.status_code == 201, response.text
        assert elapsed < 3.0, f"enrollment {index} took {elapsed:.2f}s"
        ids.append(response.json()["id"])

    assert len(set(ids)) == 10
    listed = [agent["id"] for agent in await all_agents(db_client)]
    assert all(listed.count(agent_id) == 1 for agent_id in ids)


async def test_tc05_disabled_agent_is_never_spawned(db_client: AsyncClient) -> None:
    scrubber = await enroll(
        db_client,
        name="CSV Scrubber",
        capabilities=["data.cleaning"],
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
    )
    disabled = await db_client.patch(f"/api/v1/agents/{scrubber['id']}", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"

    preview = await db_client.post(
        "/api/v1/tasks/plan", json={"request": "Clean this CSV file: a,b\n1,2"}
    )
    assert preview.status_code == 200
    plan = preview.json()
    assert scrubber["id"] not in {node["agent_id"] for node in plan["nodes"]}
    # Not offered at all: it does not even appear among the agents considered.
    assert scrubber["id"] not in plan["excluded_agents"]

    by_capability = await db_client.get("/api/v1/agents", params={"capability": "data.cleaning"})
    assert scrubber["id"] not in {agent["id"] for agent in by_capability.json()}

    forced = await db_client.post(
        "/api/v1/tasks",
        json={"request": "Clean this CSV file", "agent_ids": [scrubber["id"]]},
    )
    assert forced.status_code == 422
    assert "disabled" in forced.json()["detail"]


async def test_tc05_disabled_agent_can_be_re_enabled(db_client: AsyncClient) -> None:
    agent = await enroll(db_client, name="Toggle Agent")
    await db_client.patch(f"/api/v1/agents/{agent['id']}", json={"enabled": False})

    enabled = await db_client.patch(f"/api/v1/agents/{agent['id']}", json={"enabled": True})

    assert enabled.json()["status"] == "active"


async def test_tc05_enrolled_agent_can_be_updated(db_client: AsyncClient) -> None:
    agent = await enroll(db_client, name="Updatable Agent")

    response = await db_client.patch(
        f"/api/v1/agents/{agent['id']}",
        json={"description": "Now scores short stories.", "cost_profile": {"max_cost_usd": 0.1}},
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Now scores short stories."
    assert response.json()["max_cost_usd"] == 0.1


# ---------------------------------------------------------------------------
# US_02 Agent spawning
# ---------------------------------------------------------------------------


async def test_tc06_brief_needing_several_capabilities(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/tasks?wait=false",
        json={
            "request": (
                "Audit this code for security issues, fix the critical issues, write "
                "tests, and produce a report."
            )
        },
    )

    assert response.status_code == 200, response.text
    workflow = response.json()
    spawned = {node["agent_id"] for node in workflow["nodes"]}
    assert {"security-agent", "coding-agent", "testing-agent", "documentation-agent"} <= spawned
    # Each spawned agent is its own instance with its own id and status.
    instance_ids = [node["id"] for node in workflow["nodes"]]
    assert all(instance_ids) and len(set(instance_ids)) == len(instance_ids)
    assert all(node["status"] for node in workflow["nodes"])
    excluded = workflow["selection"]["excluded"]
    assert {"research-agent", "data-cleaner-agent", "general-agent"} <= set(excluded)
    await wait_for_run(db_client, workflow["id"])


async def test_tc07_brief_needing_one_capability(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/tasks?wait=false",
        json={"request": "Clean this CSV file:\nname,age\nbob,30\nbob,30"},
    )

    assert response.status_code == 200, response.text
    workflow = response.json()
    assert [node["agent_id"] for node in workflow["nodes"]] == ["data-cleaner-agent"]
    excluded = workflow["selection"]["excluded"]
    listed = {agent["id"] for agent in await all_agents(db_client)}
    assert set(excluded) == listed - {"data-cleaner-agent"}
    assert all(reason for reason in excluded.values())
    await wait_for_run(db_client, workflow["id"])


async def test_tc08_brief_with_no_matching_agent(db_client: AsyncClient) -> None:
    await db_client.patch("/api/v1/agents/data-cleaner-agent", json={"enabled": False})

    response = await db_client.post(
        "/api/v1/tasks", json={"request": "Clean this CSV file: a,b\n1,2"}
    )

    assert response.status_code == 422
    assert "data.cleaning" in response.json()["detail"]
    assert (await db_client.get("/api/v1/workflows")).json() == []


async def test_tc09_empty_brief_is_blocked(db_client: AsyncClient) -> None:
    response = await db_client.post("/api/v1/tasks", json={"request": ""})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "request"]


@pytest.mark.parametrize("brief", ["help me", "Please help me with something", "hi there"])
async def test_tc09_vague_brief_gets_a_clarifying_question(
    db_client: AsyncClient, brief: str
) -> None:
    response = await db_client.post("/api/v1/tasks", json={"request": brief})

    assert response.status_code == 422
    assert "What should the agents do?" in response.json()["detail"]
    assert (await db_client.get("/api/v1/workflows")).json() == []


async def test_tc10_same_brief_twice_creates_separate_instances(
    db_client: AsyncClient,
) -> None:
    brief = {"request": "Audit this repository for vulnerabilities"}

    first = (await db_client.post("/api/v1/tasks?wait=false", json=brief)).json()
    await wait_for_run(db_client, first["id"])
    second = (await db_client.post("/api/v1/tasks?wait=false", json=brief)).json()
    await wait_for_run(db_client, second["id"])

    assert first["id"] != second["id"]
    first_ids = {node["id"] for node in first["nodes"]}
    second_ids = {node["id"] for node in second["nodes"]}
    assert first_ids.isdisjoint(second_ids)
    for workflow in (first, second):
        final = (await db_client.get(f"/api/v1/workflows/{workflow['id']}")).json()
        assert final["status"] == WorkflowStatus.COMPLETED.value
        assert {node["id"] for node in final["nodes"]} == {n["id"] for n in workflow["nodes"]}


async def test_tc11_selection_reason_is_shown(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/tasks?wait=false",
        json={"request": "Audit this repository for vulnerabilities"},
    )
    workflow = response.json()

    # Why each spawned agent was chosen: the capabilities it was spawned to cover.
    assert all(node["satisfies"] for node in workflow["nodes"])
    assert "security.vulnerability_analysis" in workflow["nodes"][0]["satisfies"]
    # Why every other agent was skipped.
    excluded = workflow["selection"]["excluded"]
    assert excluded["research-agent"] == "none of its capabilities are required by this request"
    await wait_for_run(db_client, workflow["id"])


# ---------------------------------------------------------------------------
# US_03 Dynamic table creation
# ---------------------------------------------------------------------------


async def test_tc12_table_created_on_enrollment(
    db_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    agent = await enroll(db_client, name="Table Agent")

    table = table_name_for(agent["id"])
    assert agent["table_name"] == f"{AGENT_DATA_SCHEMA}.{table}"
    columns = await column_types(session_factory, table)
    assert columns["summary"] == "text"
    assert columns["score"] == "double precision"
    assert columns["passed"] == "boolean"
    assert columns["attempt_count"] == "bigint"
    assert columns["issues"] == "jsonb"
    assert {"_id", "_execution_id", "_workflow_id", "_payload", "_created_at"} <= set(columns)


async def test_tc13_unsafe_table_name_is_sanitised(
    db_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    agent = await enroll(db_client, name="x; DROP TABLE users")

    assert re.fullmatch(r"agent_data\.out_[a-z0-9_]+", agent["table_name"])
    async with session_factory() as session:
        users = await session.scalar(text("SELECT to_regclass('public.users')"))
        agents = await session.scalar(text("SELECT count(*) FROM agents"))
    assert users is not None
    assert agents and agents > 1


async def test_tc13_unsafe_property_names_are_rejected(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/agents",
        json=enrollment(
            name="Injection Columns",
            output_schema={
                "type": "object",
                "properties": {'x" text); DROP TABLE users; --': {"type": "string"}},
            },
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"].startswith("output_schema.properties.")


async def test_tc14_repeat_table_creation_keeps_data(
    db_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    agent = await enroll(db_client, name="Repeat Agent")
    table = table_name_for(agent["id"])
    async with session_factory() as session:
        await session.execute(
            text(f'INSERT INTO {AGENT_DATA_SCHEMA}."{table}" (_payload, score) VALUES (:p, 7)'),  # noqa: S608
            {"p": '{"score": 7}'},
        )
        await session.commit()

    async with session_factory() as session:
        await ensure_agent_table(session, agent["id"], SCORE_SCHEMA)
        await ensure_agent_table(session, agent["id"], SCORE_SCHEMA)
        await session.commit()
    again = await db_client.patch(
        f"/api/v1/agents/{agent['id']}", json={"output_schema": SCORE_SCHEMA}
    )
    assert again.status_code == 200

    async with session_factory() as session:
        count = await session.scalar(
            text(f'SELECT count(*) FROM {AGENT_DATA_SCHEMA}."{table}"')  # noqa: S608
        )
        tables = await session.scalar(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": AGENT_DATA_SCHEMA, "table": table},
        )
    assert count == 1
    assert tables == 1


async def test_tc14_new_schema_fields_add_columns(
    db_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    agent = await enroll(db_client, name="Evolving Agent")
    extended = {
        **SCORE_SCHEMA,
        "properties": {**SCORE_SCHEMA["properties"], "grade": {"type": "string"}},  # type: ignore[dict-item]
    }

    response = await db_client.patch(
        f"/api/v1/agents/{agent['id']}", json={"output_schema": extended}
    )

    assert response.status_code == 200
    columns = await column_types(session_factory, table_name_for(agent["id"]))
    assert columns["grade"] == "text"


async def test_tc15_table_creation_failure_rolls_back_enrollment(
    db_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_table(session: AsyncSession, *_args: object, **_kwargs: object) -> str:
        # A real database error inside the enrollment transaction.
        await session.execute(text("CREATE TABLE agent_data.broken ("))
        return "unreachable"

    monkeypatch.setattr("app.agents.seed.ensure_agent_table", failing_table)

    response = await db_client.post("/api/v1/agents", json=enrollment(name="Doomed Agent"))

    assert response.status_code == 500
    assert "rolled back" in response.json()["detail"]
    assert "Doomed Agent" not in {agent["name"] for agent in await all_agents(db_client)}
    async with session_factory() as session:
        leftover = await session.scalar(
            text("SELECT count(*) FROM agents WHERE name = 'Doomed Agent'")
        )
    assert leftover == 0


# ---------------------------------------------------------------------------
# US_04 Schema validation
# ---------------------------------------------------------------------------


async def test_tc16_invalid_json_is_rejected(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/agents",
        content=b'{"name": "Broken", "output_schema": {',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


async def test_tc16_unknown_schema_type_is_rejected_naming_the_field(
    db_client: AsyncClient,
) -> None:
    response = await db_client.post(
        "/api/v1/agents",
        json=enrollment(
            name="Bad Type Agent",
            output_schema={
                "type": "object",
                "properties": {"score": {"type": "decimal"}},
            },
        ),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith("output_schema.properties.score")
    assert "decimal" in detail
    assert "Bad Type Agent" not in {agent["name"] for agent in await all_agents(db_client)}


async def test_tc16_non_object_output_schema_is_rejected(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/agents",
        json=enrollment(name="Array Agent", output_schema={"type": "array"}),
    )

    assert response.status_code == 422
    assert response.json()["detail"].startswith("output_schema.type")


async def run_enrolled(
    client: AsyncClient, provider: FakeProvider, payloads: list[dict[str, object]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    agent = await enroll(client, name=f"Runner {uuid.uuid4().hex[:6]}")
    for payload in payloads:
        provider.queue_json(payload)
    response = await client.post(
        "/api/v1/tasks",
        json={"request": "Score this essay: It was a dark night.", "agent_ids": [agent["id"]]},
    )
    assert response.status_code == 200, response.text
    return agent, response.json()


async def test_tc17_valid_output_is_written_to_the_agent_table(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    agent, workflow = await run_enrolled(
        db_client,
        fake_provider,
        [{"summary": "Solid", "score": 8.5, "passed": True, "attempt_count": 1, "issues": []}],
    )

    assert workflow["status"] == WorkflowStatus.COMPLETED.value
    stored = (await db_client.get(f"/api/v1/agents/{agent['id']}/records")).json()
    assert stored["table"] == agent["table_name"]
    assert len(stored["records"]) == 1
    row = stored["records"][0]
    assert row["score"] == 8.5
    assert row["passed"] is True
    assert row["attempt_count"] == 1
    assert row["_workflow_id"] == workflow["id"]


async def test_tc18_output_missing_a_required_field(
    db_client: AsyncClient,
    fake_provider: FakeProvider,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = LogRecorder()
    monkeypatch.setattr("app.services.agent_executor.logger", recorder)
    agent, workflow = await run_enrolled(
        db_client, fake_provider, [{"summary": "No score here"}] * 8
    )

    assert workflow["status"] == WorkflowStatus.FAILED.value
    node = workflow["nodes"][0]
    assert node["status"] == NodeStatus.FAILED.value
    assert node["executions"]
    assert all(
        execution["status"] == ExecutionStatus.INVALID_OUTPUT.value
        for execution in node["executions"]
    )
    assert "score" in node["executions"][-1]["error_message"]

    # Nothing is stored: not in the agent's table, and not as result data.
    stored = (await db_client.get(f"/api/v1/agents/{agent['id']}/records")).json()
    assert stored["records"] == []
    async with session_factory() as session:
        results = (await session.execute(select(AgentResultRecord))).scalars().all()
    assert results and all(result.payload == {} for result in results)
    assert all(result.schema_valid is False for result in results)

    logged = [fields for event, fields in recorder.events if event == "agent_output_invalid"]
    assert logged
    assert logged[0]["agent_id"] == agent["id"]
    assert logged[0]["fields"] == ["score"]


async def test_tc19_output_with_the_wrong_data_type(
    db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    agent, workflow = await run_enrolled(
        db_client, fake_provider, [{"summary": "Typed wrong", "score": "high"}] * 8
    )

    assert workflow["status"] == WorkflowStatus.FAILED.value
    error = workflow["nodes"][0]["executions"][-1]["error_message"]
    assert error.startswith("score:")
    assert "'number'" in error
    stored = (await db_client.get(f"/api/v1/agents/{agent['id']}/records")).json()
    assert stored["records"] == []
