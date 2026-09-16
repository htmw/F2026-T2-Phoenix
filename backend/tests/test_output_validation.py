"""Output parsing and validation: the trust boundary for model output."""

from __future__ import annotations

import json

import httpx
import pytest

from app.providers.openai_compatible import OpenAIProvider
from app.schemas.execution import AgentInput, UpstreamResult
from app.services.output_validation import extract_json_object, validate_agent_output
from app.services.prompting import MAX_UPSTREAM_CHARS, build_user_prompt
from tests.test_providers import request_for, stub_transport

SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["answer"],
    "properties": {"answer": {"type": "string"}, "count": {"type": "integer"}},
}


def test_plain_json_parses() -> None:
    payload, error, recovered = extract_json_object('{"answer": "yes"}')

    assert payload == {"answer": "yes"}
    assert error is None
    assert recovered is False


def test_fenced_json_is_recovered() -> None:
    payload, _, recovered = extract_json_object('```json\n{"answer": "yes"}\n```')

    assert payload == {"answer": "yes"}
    assert recovered is True


def test_unlabelled_fence_is_recovered() -> None:
    payload, _, _ = extract_json_object('```\n{"answer": "yes"}\n```')

    assert payload == {"answer": "yes"}


def test_prose_around_json_is_recovered() -> None:
    payload, _, recovered = extract_json_object(
        'Certainly! Here is the result:\n{"answer": "yes"}\nLet me know if you need more.'
    )

    assert payload == {"answer": "yes"}
    assert recovered is True


def test_empty_output_is_reported_clearly() -> None:
    payload, error, _ = extract_json_object("   ")

    assert payload is None
    assert error == "model returned empty output"


def test_prose_only_output_fails() -> None:
    payload, error, _ = extract_json_object("I'm not able to help with that.")

    assert payload is None
    assert error is not None


def test_a_json_array_is_rejected() -> None:
    # Agents must return objects: downstream input is built from named fields.
    payload, error, _ = extract_json_object('["a", "b"]')

    assert payload is None
    assert error is not None


def test_truncated_json_fails_rather_than_guessing() -> None:
    payload, _, _ = extract_json_object('{"answer": "yes", "cou')

    assert payload is None


def test_valid_payload_passes_schema_validation() -> None:
    outcome = validate_agent_output('{"answer": "yes", "count": 2}', SCHEMA)

    assert outcome.valid is True
    assert outcome.payload == {"answer": "yes", "count": 2}


def test_missing_required_field_is_described() -> None:
    outcome = validate_agent_output('{"count": 2}', SCHEMA)

    assert outcome.valid is False
    assert outcome.error is not None
    # The message is fed back to the model on retry, so it has to name the problem.
    assert "answer" in outcome.error


def test_wrong_type_is_described_with_its_location() -> None:
    outcome = validate_agent_output('{"answer": "yes", "count": "two"}', SCHEMA)

    assert outcome.valid is False
    assert outcome.error is not None
    assert "count" in outcome.error


def test_nested_error_location_is_reported() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["severity"],
                    "properties": {"severity": {"enum": ["high", "low"]}},
                },
            }
        },
    }

    outcome = validate_agent_output('{"items": [{"severity": "catastrophic"}]}', schema)

    assert outcome.valid is False
    assert outcome.error is not None
    assert "items/0/severity" in outcome.error


def test_many_errors_are_summarised_not_dumped() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "required": [f"field{i}" for i in range(10)],
        "properties": {f"field{i}": {"type": "string"} for i in range(10)},
    }

    outcome = validate_agent_output("{}", schema)

    assert outcome.error is not None
    assert "and 5 more" in outcome.error


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def test_oversized_upstream_payload_is_truncated_visibly() -> None:
    import uuid

    huge = {"blob": "x" * (MAX_UPSTREAM_CHARS * 2)}
    agent_input = AgentInput(
        task_id=uuid.uuid4(),
        node_key="downstream",
        agent_id="documentation-agent",
        objective="Summarise the findings",
        upstream=(UpstreamResult(node_key="up", agent_id="research-agent", payload=huge),),
    )

    prompt = build_user_prompt(agent_input)

    # Silently dropping data would let the agent reason confidently about material it
    # never received, so the truncation is stated in the prompt.
    assert "[truncated:" in prompt
    assert len(prompt) < MAX_UPSTREAM_CHARS * 2


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def sse(*chunks: str) -> str:
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": chunk}}]}) for chunk in chunks
    ]
    lines.append("data: [DONE]")
    return "\n\n".join(lines)


async def test_streamed_chunks_are_yielded_in_order() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse("Hel", "lo ", "world"))

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))

    chunks = [chunk async for chunk in provider.stream(request_for(provider.models[0]))]

    assert "".join(chunks) == "Hello world"


async def test_stream_ignores_keepalives_and_terminators() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        body = "\n\n".join([": keep-alive", "data: {}", "data: [DONE]", 'data: {"bad json'])
        return httpx.Response(200, text=body)

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))

    chunks = [chunk async for chunk in provider.stream(request_for(provider.models[0]))]

    assert chunks == []


async def test_stream_error_status_is_mapped_before_any_chunk() -> None:
    from app.domain.enums import ErrorKind
    from app.providers.base import ProviderError

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    provider = OpenAIProvider("sk-test", client=stub_transport(handler))

    with pytest.raises(ProviderError) as caught:
        async for _ in provider.stream(request_for(provider.models[0])):
            pass

    assert caught.value.kind is ErrorKind.RATE_LIMITED
