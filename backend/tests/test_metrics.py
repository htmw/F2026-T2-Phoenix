"""Operator metrics: the five questions, from Postgres and from the scrape endpoint."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import ProcessMetrics
from app.domain.enums import ErrorKind
from app.providers.fake import FakeProvider
from app.services.metrics_service import MetricsRepository
from tests.test_retry_and_recovery import run_plan, seed_fast_retries, single_node_plan


async def test_metrics_summary_answers_the_operator_questions(
    seeded_session: AsyncSession, db_client: AsyncClient, fake_provider: FakeProvider
) -> None:
    fake_provider.queue_json({"findings": []})
    submitted = await db_client.post(
        "/api/v1/tasks", json={"request": "Find security vulnerabilities in the payments service"}
    )
    assert submitted.status_code == 200

    response = await db_client.get("/api/v1/metrics")
    assert response.status_code == 200
    body = response.json()

    assert body["workflow_count"] >= 1
    assert body["attempt_count"] >= 1
    assert body["total_cost_usd"] >= 0
    assert body["token_totals"]["total"] >= body["token_totals"]["input"]
    assert body["slowest_agent"] is not None
    assert body["slowest_agent"]["agent_id"] == "security-agent"


async def test_prometheus_scrape_is_plain_text(db_client: AsyncClient) -> None:
    response = await db_client.get("/metrics")
    assert response.status_code == 200
    assert "agentorch_executions_total" in response.text
    assert response.headers["content-type"].startswith("text/plain")


async def test_retries_and_failures_show_up_in_the_summary(
    seeded_session: AsyncSession,
) -> None:
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.TIMEOUT, "too slow")
    provider.queue_json({"findings": []})

    await seed_fast_retries(seeded_session)
    await run_plan(seeded_session, provider, single_node_plan())
    await seeded_session.commit()

    summary = await MetricsRepository(seeded_session).summary()
    retries = summary["retry_counts"]
    tokens = summary["token_totals"]
    assert isinstance(retries, dict)
    assert isinstance(tokens, dict)
    assert retries.get("security-agent", 0) >= 1
    assert int(tokens["total"]) > 0


def test_prometheus_renderer_escapes_labels() -> None:
    metrics = ProcessMetrics()
    metrics.observe(
        status="succeeded",
        provider='fake"x',
        cost_usd=0.1,
        input_tokens=3,
        output_tokens=2,
        attempt=2,
        error_kind=None,
    )
    text = metrics.render_prometheus()
    assert 'provider="fake\\"x"' in text
    assert "agentorch_retries_total 1" in text


async def test_failed_provider_is_named(seeded_session: AsyncSession) -> None:
    await seed_fast_retries(seeded_session)
    provider = FakeProvider()
    for _ in range(3):
        provider.queue_failure(ErrorKind.AUTHENTICATION, "bad key")
    await run_plan(seeded_session, provider, single_node_plan())
    await seeded_session.commit()

    summary = await MetricsRepository(seeded_session).summary()
    failing = summary["failing_providers"]
    assert isinstance(failing, dict)
    assert failing.get("fake", 0) >= 1
