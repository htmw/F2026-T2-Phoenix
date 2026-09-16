"""Domain contract tests: graph validation, retry maths, and hand-off shape."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.agents.builtin import CODING_AGENT
from app.domain.enums import Capability, ErrorKind, ExecutionStatus
from app.schemas.agent import AgentDefinition, AgentSummary, RetryPolicy
from app.schemas.execution import (
    AgentInput,
    ExecutionError,
    TokenUsage,
    UpstreamResult,
)
from app.schemas.workflow import (
    Approval,
    EdgeCondition,
    TaskRequest,
    WorkflowEdge,
    WorkflowNode,
    WorkflowPlan,
)


def node(key: str, agent_id: str = "coding-agent") -> WorkflowNode:
    return WorkflowNode(key=key, agent_id=agent_id, objective="do work")


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------


def test_agent_requires_at_least_one_capability() -> None:
    with pytest.raises(ValidationError):
        AgentDefinition(
            id="empty-agent",
            name="Empty",
            description="No capabilities.",
            capabilities=frozenset(),
            instructions="x",
            output_schema={"type": "object"},
        )


def test_agent_output_schema_must_describe_an_object() -> None:
    # Downstream inputs are built from named fields, so a top-level array or string
    # would make hand-offs impossible.
    with pytest.raises(ValidationError, match="must describe an object"):
        AgentDefinition(
            id="array-agent",
            name="Array",
            description="Returns an array.",
            capabilities=frozenset({Capability.SUMMARISATION}),
            instructions="x",
            output_schema={"type": "array"},
        )


def test_agent_id_rejects_unsafe_characters() -> None:
    with pytest.raises(ValidationError):
        AgentDefinition(
            id="Bad Agent/../etc",
            name="Bad",
            description="Bad id.",
            capabilities=frozenset({Capability.SUMMARISATION}),
            instructions="x",
            output_schema={"type": "object"},
        )


def test_agent_summary_excludes_instructions() -> None:
    summary = AgentSummary.from_definition(CODING_AGENT)

    assert "instructions" not in summary.model_dump()
    assert summary.capabilities == sorted(CODING_AGENT.capabilities)
    assert summary.model_strategy == "auto"
    assert summary.preferred_provider is None
    assert summary.preferred_model is None


def test_task_request_accepts_agent_and_model_overrides() -> None:
    request = TaskRequest(
        request="Fix the login handler",
        agent_ids=["coding-agent", "testing-agent"],
        model_overrides={"coding-agent": "openai:gpt-4o"},
    )

    assert request.agent_ids == ["coding-agent", "testing-agent"]
    assert request.model_overrides["coding-agent"] == "openai:gpt-4o"
    assert request.routing_strategy.value == "mixed"


def test_task_request_one_strategy_requires_shared_model() -> None:
    request = TaskRequest(
        request="Fix the login handler now",
        routing_strategy="one",
        shared_model="openai:gpt-4o",
    )
    assert request.routing_strategy.value == "one"
    assert request.shared_model == "openai:gpt-4o"


def test_provides_reports_capability_membership() -> None:
    assert CODING_AGENT.provides(Capability.DEBUGGING) is True
    assert CODING_AGENT.provides(Capability.VULNERABILITY_ANALYSIS) is False


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


def test_first_attempt_has_no_backoff() -> None:
    assert RetryPolicy().backoff_for_attempt(1) == 0.0


def test_backoff_grows_geometrically() -> None:
    policy = RetryPolicy(initial_backoff_seconds=1.0, backoff_multiplier=2.0)

    assert policy.backoff_for_attempt(2) == 1.0
    assert policy.backoff_for_attempt(3) == 2.0
    assert policy.backoff_for_attempt(4) == 4.0


def test_backoff_is_capped() -> None:
    policy = RetryPolicy(
        initial_backoff_seconds=10.0, backoff_multiplier=10.0, max_backoff_seconds=15.0
    )

    assert policy.backoff_for_attempt(5) == 15.0


def test_retry_policy_rejects_zero_attempts() -> None:
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=0)


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


def test_transient_errors_are_retryable() -> None:
    assert ExecutionError(kind=ErrorKind.RATE_LIMITED, message="slow down").is_retryable
    assert ExecutionError(kind=ErrorKind.TIMEOUT, message="too slow").is_retryable


def test_permanent_errors_are_not_retryable() -> None:
    # Retrying a bad key or a malformed request just burns money and latency.
    assert not ExecutionError(kind=ErrorKind.AUTHENTICATION, message="bad key").is_retryable
    assert not ExecutionError(kind=ErrorKind.INVALID_REQUEST, message="bad body").is_retryable
    assert not ExecutionError(kind=ErrorKind.BUDGET_EXCEEDED, message="too dear").is_retryable


def test_an_adapter_can_override_the_taxonomy_default() -> None:
    error = ExecutionError(kind=ErrorKind.INVALID_REQUEST, message="transient 400", retryable=True)

    assert error.is_retryable is True


# ---------------------------------------------------------------------------
# Structured hand-off
# ---------------------------------------------------------------------------


def test_agent_input_carries_only_named_upstream_payloads() -> None:
    agent_input = AgentInput(
        task_id=uuid.uuid4(),
        node_key="coding",
        agent_id="coding-agent",
        objective="fix the vulnerabilities",
        upstream=(
            UpstreamResult(
                node_key="security",
                agent_id="security-agent",
                payload={"findings": [{"severity": "high", "issue": "SQL injection"}]},
            ),
        ),
    )

    payload = agent_input.upstream_payload("security")
    assert payload is not None
    assert payload["findings"][0]["issue"] == "SQL injection"  # type: ignore[index]
    # No transcript, no message history: only declared structured fields.
    assert "messages" not in agent_input.model_dump()


def test_missing_upstream_payload_returns_none() -> None:
    agent_input = AgentInput(
        task_id=uuid.uuid4(), node_key="a", agent_id="coding-agent", objective="x"
    )

    assert agent_input.upstream_payload("nope") is None


def test_token_usage_adds_and_totals() -> None:
    combined = TokenUsage(input_tokens=100, output_tokens=50) + TokenUsage(
        input_tokens=10, output_tokens=5
    )

    assert (combined.input_tokens, combined.output_tokens) == (110, 55)
    assert combined.total_tokens == 165


def test_execution_status_success_helper() -> None:
    from app.schemas.execution import AgentOutput

    assert AgentOutput(agent_id="a", node_key="n", status=ExecutionStatus.SUCCEEDED).succeeded
    assert not AgentOutput(agent_id="a", node_key="n", status=ExecutionStatus.FAILED).succeeded


# ---------------------------------------------------------------------------
# Workflow graph validation
# ---------------------------------------------------------------------------


def test_single_node_plan_is_valid() -> None:
    plan = WorkflowPlan(nodes=(node("only"),))

    assert plan.roots() == ("only",)
    assert plan.dependencies_of("only") == ()


def test_duplicate_node_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate node keys"):
        WorkflowPlan(nodes=(node("a"), node("a")))


def test_edge_to_unknown_node_is_rejected() -> None:
    with pytest.raises(ValidationError, match="is not a node"):
        WorkflowPlan(nodes=(node("a"),), edges=(WorkflowEdge(source="a", target="ghost"),))


def test_self_loop_is_rejected() -> None:
    with pytest.raises(ValidationError, match="points at itself"):
        WorkflowPlan(nodes=(node("a"),), edges=(WorkflowEdge(source="a", target="a"),))


def test_cycle_is_rejected() -> None:
    # A cycle would deadlock the executor: every node waits on a dependency that can
    # never complete. Rejecting at construction turns a hang into a clear error.
    with pytest.raises(ValidationError, match="cycle"):
        WorkflowPlan(
            nodes=(node("a"), node("b"), node("c")),
            edges=(
                WorkflowEdge(source="a", target="b"),
                WorkflowEdge(source="b", target="c"),
                WorkflowEdge(source="c", target="a"),
            ),
        )


def test_diamond_graph_is_valid_and_reports_dependencies() -> None:
    plan = WorkflowPlan(
        nodes=(node("plan"), node("security"), node("deps"), node("analysis")),
        edges=(
            WorkflowEdge(source="plan", target="security"),
            WorkflowEdge(source="plan", target="deps"),
            WorkflowEdge(source="security", target="analysis"),
            WorkflowEdge(source="deps", target="analysis"),
        ),
    )

    assert plan.roots() == ("plan",)
    assert set(plan.dependencies_of("analysis")) == {"security", "deps"}


def test_plan_requires_at_least_one_node() -> None:
    with pytest.raises(ValidationError):
        WorkflowPlan(nodes=())


def test_conditional_edge_carries_its_condition() -> None:
    plan = WorkflowPlan(
        nodes=(node("security"), node("coding")),
        edges=(
            WorkflowEdge(
                source="security",
                target="coding",
                condition=EdgeCondition(
                    path="findings",
                    operator="non_empty",
                    description="only fix code when something was found",
                ),
            ),
        ),
    )

    edge = plan.edges[0]
    assert edge.condition is not None
    assert edge.condition.operator == "non_empty"


def test_task_request_rejects_an_empty_request() -> None:
    with pytest.raises(ValidationError):
        TaskRequest(request="hi")


def test_approval_records_the_actor_and_decision() -> None:
    workflow_id = uuid.uuid4()
    approval = Approval(
        workflow_id=workflow_id, node_key="coding", approved=True, decided_by="operator"
    )

    dumped = approval.model_dump()
    assert dumped["approved"] is True
    assert dumped["decided_by"] == "operator"
    assert dumped["node_key"] == "coding"
