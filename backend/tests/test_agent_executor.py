"""Agent executor tests.

Every path an agent can take is covered here with a scripted provider: success, invalid
output, timeout, provider failure, budget refusal, and unroutable model. These are the
paths the workflow engine will make retry decisions from, so they must return data
rather than raise.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app.agents.builtin import SECURITY_AGENT
from app.domain.enums import Capability, ErrorKind, ExecutionStatus, ModelTrait
from app.providers.base import CompletionRequest, CompletionResponse, ModelSpec
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.schemas.agent import AgentDefinition, AgentLimits, ModelPreference
from app.schemas.execution import AgentInput, TokenUsage
from app.services.agent_executor import AgentExecutor, ExecutionContext

SIMPLE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["answer"],
    "properties": {"answer": {"type": "string"}, "score": {"type": "integer"}},
}


def simple_agent(**overrides: object) -> AgentDefinition:
    defaults: dict[str, object] = {
        "id": "simple-agent",
        "name": "Simple",
        "description": "A test agent.",
        "capabilities": frozenset({Capability.SUMMARISATION}),
        "instructions": "Answer the question.",
        "output_schema": SIMPLE_SCHEMA,
        "model_preference": ModelPreference(min_context_tokens=1_000),
    }
    defaults.update(overrides)
    return AgentDefinition(**defaults)


def input_for(agent: AgentDefinition, **overrides: object) -> AgentInput:
    defaults: dict[str, object] = {
        "task_id": uuid.uuid4(),
        "node_key": "main",
        "agent_id": agent.id,
        "objective": "What is the answer?",
    }
    defaults.update(overrides)
    return AgentInput(**defaults)


def executor_with(provider: FakeProvider) -> AgentExecutor:
    return AgentExecutor(ProviderRegistry([provider]))


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


async def test_valid_output_is_returned_as_a_payload() -> None:
    provider = FakeProvider()
    provider.queue_json({"answer": "forty-two", "score": 42})
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.status is ExecutionStatus.SUCCEEDED
    assert output.payload == {"answer": "forty-two", "score": 42}
    assert output.error is None


async def test_success_records_usage_cost_and_latency() -> None:
    provider = FakeProvider()
    provider.queue_json({"answer": "ok"})
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.usage.total_tokens > 0
    assert output.cost_usd > 0
    assert output.latency_ms >= 0
    assert output.provider == "fake"
    assert output.model is not None
    assert output.routing_reason  # why this model was chosen
    assert isinstance(output.routing_alternatives, tuple)


async def test_summary_is_extracted_when_the_agent_provides_one() -> None:
    provider = FakeProvider()
    provider.queue_json({"answer": "ok", "summary": "Everything checks out."})
    agent = simple_agent(
        output_schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}, "summary": {"type": "string"}},
        }
    )

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.summary == "Everything checks out."


async def test_json_wrapped_in_a_code_fence_is_recovered() -> None:
    provider = FakeProvider(default_response='```json\n{"answer": "fenced"}\n```')
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    # Models wrap output in fences despite instructions; recovering is far cheaper than
    # burning a retry.
    assert output.status is ExecutionStatus.SUCCEEDED
    assert output.payload == {"answer": "fenced"}


async def test_prompt_contains_the_objective_and_the_schema() -> None:
    provider = FakeProvider()
    provider.queue_json({"answer": "ok"})
    agent = simple_agent()

    await executor_with(provider).execute(agent, input_for(agent, objective="Find the bug"))

    request = provider.requests[0]
    assert "Find the bug" in request.user_prompt
    assert "answer" in request.system_prompt
    assert agent.instructions in request.system_prompt


async def test_upstream_results_are_passed_as_structured_sections() -> None:
    provider = FakeProvider()
    provider.queue_json({"answer": "ok"})
    agent = simple_agent()
    from app.schemas.execution import UpstreamResult

    await executor_with(provider).execute(
        agent,
        input_for(
            agent,
            upstream=(
                UpstreamResult(
                    node_key="security",
                    agent_id="security-agent",
                    payload={"findings": [{"severity": "high", "issue": "SQL injection"}]},
                ),
            ),
        ),
    )

    prompt = provider.requests[0].user_prompt
    assert "security-agent" in prompt
    assert "SQL injection" in prompt
    # No transcript: the hand-off carries the payload, not a conversation.
    assert "assistant:" not in prompt.lower()


async def test_feedback_is_labelled_for_the_agent() -> None:
    provider = FakeProvider()
    provider.queue_json({"answer": "ok"})
    agent = simple_agent()

    await executor_with(provider).execute(
        agent, input_for(agent, attempt=2, feedback="test_login failed: null pointer")
    )

    prompt = provider.requests[0].user_prompt
    assert "Required corrections" in prompt
    assert "test_login failed" in prompt
    assert "attempt 2" in prompt


# ---------------------------------------------------------------------------
# Invalid output
# ---------------------------------------------------------------------------


async def test_non_json_output_is_invalid_not_an_exception() -> None:
    provider = FakeProvider(default_response="I'm afraid I can't do that.")
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.status is ExecutionStatus.INVALID_OUTPUT
    assert output.error is not None
    assert output.error.kind is ErrorKind.INVALID_OUTPUT
    # Retryable: a different sample from the same model may well conform.
    assert output.error.is_retryable is True


async def test_output_missing_a_required_field_is_invalid() -> None:
    provider = FakeProvider()
    provider.queue_json({"score": 10})
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.status is ExecutionStatus.INVALID_OUTPUT
    assert output.error is not None
    assert "answer" in output.error.message


async def test_output_with_a_wrong_type_is_invalid() -> None:
    provider = FakeProvider()
    provider.queue_json({"answer": "ok", "score": "not-a-number"})
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.status is ExecutionStatus.INVALID_OUTPUT


async def test_invalid_output_still_records_the_spend() -> None:
    provider = FakeProvider(default_response="garbage")
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    # The call was made and billed; pretending it was free would understate cost.
    assert output.cost_usd > 0


async def test_invalid_output_preserves_the_raw_text_for_debugging() -> None:
    provider = FakeProvider(default_response="total nonsense")
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.error is not None
    assert output.error.details["raw_output"] == "total nonsense"


# ---------------------------------------------------------------------------
# Provider failures
# ---------------------------------------------------------------------------


async def test_provider_failure_is_returned_as_a_classified_error() -> None:
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.PROVIDER_UNAVAILABLE, "upstream is down")
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.status is ExecutionStatus.FAILED
    assert output.error is not None
    assert output.error.kind is ErrorKind.PROVIDER_UNAVAILABLE
    assert output.error.is_retryable is True


async def test_authentication_failure_is_not_retryable() -> None:
    provider = FakeProvider()
    provider.queue_failure(ErrorKind.AUTHENTICATION, "bad key")
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.error is not None
    assert output.error.is_retryable is False


async def test_unroutable_model_requirement_fails_without_a_call() -> None:
    provider = FakeProvider()
    agent = simple_agent(model_preference=ModelPreference(min_context_tokens=10_000_000))

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.status is ExecutionStatus.FAILED
    assert output.error is not None
    assert output.error.kind is ErrorKind.PROVIDER_UNAVAILABLE
    assert output.error.is_retryable is False
    assert provider.requests == []


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class SlowProvider(FakeProvider):
    """A provider that takes longer than the agent's timeout allows."""

    async def generate(self, request: CompletionRequest) -> CompletionResponse:
        await asyncio.sleep(5)
        return await super().generate(request)


async def test_timeout_is_enforced_by_the_executor() -> None:
    provider = SlowProvider()
    agent = simple_agent(limits=AgentLimits(timeout_seconds=0.05, max_cost_usd=1.0))

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.status is ExecutionStatus.TIMED_OUT
    assert output.error is not None
    assert output.error.kind is ErrorKind.TIMEOUT
    # Retryable: a hung request often succeeds on a second attempt.
    assert output.error.is_retryable is True


# ---------------------------------------------------------------------------
# Cost ceilings
# ---------------------------------------------------------------------------


EXPENSIVE_MODEL = ModelSpec(
    id="fake:lavish",
    provider="fake",
    model_name="fake-lavish",
    traits=frozenset({ModelTrait.REASONING, ModelTrait.STRUCTURED_OUTPUT}),
    context_tokens=100_000,
    max_output_tokens=100_000,
    input_cost_per_million=500.0,
    output_cost_per_million=1_000.0,
)


async def test_agent_cost_ceiling_prevents_the_call() -> None:
    provider = FakeProvider(models=(EXPENSIVE_MODEL,))
    agent = simple_agent(
        limits=AgentLimits(timeout_seconds=30.0, max_cost_usd=0.01),
        model_preference=ModelPreference(min_context_tokens=1_000, max_output_tokens=100_000),
    )

    output = await executor_with(provider).execute(agent, input_for(agent))

    assert output.status is ExecutionStatus.BUDGET_EXCEEDED
    assert output.error is not None
    assert output.error.kind is ErrorKind.BUDGET_EXCEEDED
    assert output.error.is_retryable is False
    # Refusing before spending is the whole point.
    assert provider.requests == []
    assert output.cost_usd == 0.0


async def test_workflow_budget_ceiling_prevents_the_call() -> None:
    provider = FakeProvider()
    # The agent's own ceiling is generous; the workflow's remaining budget is what bites,
    # which is the case that stops a long workflow from overspending late in its run.
    agent = simple_agent(limits=AgentLimits(timeout_seconds=30.0, max_cost_usd=10.0))

    output = await executor_with(provider).execute(
        agent, input_for(agent), ExecutionContext(remaining_budget_usd=0.0000001)
    )

    assert output.status is ExecutionStatus.BUDGET_EXCEEDED
    assert output.error is not None
    assert "remaining budget" in output.error.message
    assert provider.requests == []


async def test_affordable_call_proceeds() -> None:
    provider = FakeProvider()
    provider.queue_json({"answer": "ok"})
    agent = simple_agent()

    output = await executor_with(provider).execute(
        agent, input_for(agent), ExecutionContext(remaining_budget_usd=50.0)
    )

    assert output.status is ExecutionStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# A real built-in agent end to end
# ---------------------------------------------------------------------------


async def test_security_agent_accepts_an_empty_findings_list() -> None:
    """An empty result is a valid, meaningful answer, not a failure.

    The conditional-skip behaviour in Sprint 5 depends on this: "no vulnerabilities
    found" must validate so the workflow can decide to skip the coding agent.
    """
    provider = FakeProvider()
    provider.queue_json({"findings": [], "summary": "No issues found."})

    output = await executor_with(provider).execute(
        SECURITY_AGENT, input_for(SECURITY_AGENT, objective="Audit the repo")
    )

    assert output.status is ExecutionStatus.SUCCEEDED
    assert output.payload["findings"] == []


async def test_security_agent_rejects_a_finding_without_severity() -> None:
    provider = FakeProvider()
    provider.queue_json({"findings": [{"issue": "something vague"}]})

    output = await executor_with(provider).execute(
        SECURITY_AGENT, input_for(SECURITY_AGENT, objective="Audit the repo")
    )

    # Severity drives later branching, so a finding without it cannot be trusted.
    assert output.status is ExecutionStatus.INVALID_OUTPUT


async def test_security_agent_findings_round_trip() -> None:
    finding = {
        "severity": "high",
        "file": "auth.js",
        "issue": "SQL injection",
        "recommendation": "Use parameterized queries",
    }
    provider = FakeProvider()
    provider.queue_json({"findings": [finding]})

    output = await executor_with(provider).execute(
        SECURITY_AGENT, input_for(SECURITY_AGENT, objective="Audit the repo")
    )

    assert output.payload["findings"] == [finding]


def test_token_usage_cost_arithmetic() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)

    assert EXPENSIVE_MODEL.cost_for(usage) == pytest.approx(1_500.0)


async def test_scripted_response_can_depend_on_the_request() -> None:
    provider = FakeProvider()
    provider.queue_response(
        lambda request: json.dumps({"answer": request.user_prompt.splitlines()[1]})
    )
    agent = simple_agent()

    output = await executor_with(provider).execute(agent, input_for(agent, objective="echo me"))

    assert output.payload == {"answer": "echo me"}


async def test_provider_unavailability_falls_back_to_the_next_model() -> None:
    from collections.abc import AsyncIterator

    from app.providers.base import (
        LLMProvider,
        ModelSpec,
        ProviderError,
    )
    from app.providers.registry import ProviderRegistry

    cheap = ModelSpec(
        id="down:cheap",
        provider="down",
        model_name="down-cheap",
        traits=frozenset({ModelTrait.STRUCTURED_OUTPUT, ModelTrait.FAST, ModelTrait.CHEAP}),
        context_tokens=32_000,
        max_output_tokens=1_024,
        input_cost_per_million=0.01,
        output_cost_per_million=0.01,
        typical_latency_ms=100,
    )

    class DownProvider(LLMProvider):
        name = "down"

        def get_model_capabilities(self) -> tuple[ModelSpec, ...]:
            return (cheap,)

        def estimate_cost(self, _request: CompletionRequest) -> float:
            return 0.001

        def validate_configuration(self) -> None:
            return None

        async def stream(self, _request: CompletionRequest) -> AsyncIterator[str]:
            for _ in ():
                yield ""

        async def generate(self, _request: CompletionRequest) -> CompletionResponse:
            raise ProviderError(
                ErrorKind.PROVIDER_UNAVAILABLE, "down for maintenance", provider=self.name
            )

    backup = FakeProvider()
    backup.queue_json({"answer": "from-backup"})
    agent = simple_agent()
    output = await AgentExecutor(ProviderRegistry([DownProvider(), backup])).execute(
        agent, input_for(agent)
    )

    assert output.status is ExecutionStatus.SUCCEEDED
    assert output.payload == {"answer": "from-backup"}
    assert output.provider == "fake"
