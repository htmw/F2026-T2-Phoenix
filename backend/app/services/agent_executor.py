"""Executing a single agent attempt.

One attempt in, one ``AgentOutput`` out. Failures are returned as outcomes carrying a
classified error rather than raised, because the caller — the workflow engine — must
decide whether to retry, skip, replace, or escalate, and that decision needs data, not
an exception.

Retry loops, conditional branching, and scheduling live in the workflow engine. This
module deliberately knows nothing about graphs.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.domain.enums import ErrorKind, ExecutionStatus
from app.providers.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    ModelSpec,
    ProviderError,
)
from app.providers.registry import NoSuitableModelError, ProviderRegistry
from app.schemas.agent import AgentDefinition
from app.schemas.execution import AgentInput, AgentOutput, ExecutionError, TokenUsage
from app.services.output_validation import validate_agent_output
from app.services.prompting import build_system_prompt, build_user_prompt

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Limits imposed by the caller on top of the agent's own limits."""

    #: Remaining budget for the whole workflow, if one was set.
    remaining_budget_usd: float | None = None


class AgentExecutor:
    def __init__(self, providers: ProviderRegistry) -> None:
        self._providers = providers

    async def execute(
        self,
        agent: AgentDefinition,
        agent_input: AgentInput,
        context: ExecutionContext | None = None,
    ) -> AgentOutput:
        context = context or ExecutionContext()
        started_at = datetime.now(UTC)
        started = time.perf_counter()

        log = logger.bind(
            agent_id=agent.id,
            node_key=agent_input.node_key,
            task_id=str(agent_input.task_id),
            attempt=agent_input.attempt,
        )

        try:
            ranked = self._providers.rank_models(agent.model_preference)
        except NoSuitableModelError as exc:
            log.warning("model_selection_failed", error=str(exc))
            return self._failure(
                agent,
                agent_input,
                ExecutionError(
                    kind=ErrorKind.PROVIDER_UNAVAILABLE, message=str(exc), retryable=False
                ),
                started_at,
                started,
            )

        last_error: AgentOutput | None = None
        skipped_providers: set[str] = set()
        for index, decision in enumerate(ranked):
            provider, model = decision.provider, decision.model
            if provider.name in skipped_providers:
                continue
            output = await self._attempt(
                agent,
                agent_input,
                context,
                provider,
                model,
                decision.reason,
                started_at,
                started,
                log,
            )
            alternatives = tuple(
                f"{item.provider.name}:{item.model.id}"
                for item in ranked[index + 1 : index + 6]
                if item.provider.name not in skipped_providers
            )
            annotated = output.model_copy(
                update={
                    "routing_reason": decision.reason,
                    "routing_alternatives": alternatives,
                }
            )
            if annotated.succeeded:
                return annotated
            last_error = annotated
            if not _can_fallback(annotated):
                return annotated
            skipped_providers.add(provider.name)
            nxt = next(
                (
                    item
                    for item in ranked[index + 1 :]
                    if item.provider.name not in skipped_providers
                ),
                None,
            )
            if nxt is None:
                return annotated
            log.warning(
                "provider_fallback",
                from_provider=provider.name,
                from_model=model.id,
                to_provider=nxt.provider.name,
                to_model=nxt.model.id,
                error_kind=annotated.error.kind.value if annotated.error else None,
            )

        return last_error or self._failure(
            agent,
            agent_input,
            ExecutionError(kind=ErrorKind.UNKNOWN, message="no provider produced a result"),
            started_at,
            started,
        )

    async def _attempt(
        self,
        agent: AgentDefinition,
        agent_input: AgentInput,
        context: ExecutionContext,
        provider: LLMProvider,
        model: ModelSpec,
        reason: str,
        started_at: datetime,
        started: float,
        log: Any,
    ) -> AgentOutput:
        request = self._build_request(agent, agent_input, model)

        estimate = provider.estimate_cost(request)
        if (budget_error := self._check_budget(agent, context, estimate)) is not None:
            log.warning(
                "budget_check_failed",
                estimated_cost_usd=round(estimate, 6),
                agent_limit_usd=agent.limits.max_cost_usd,
                provider=provider.name,
                model=model.id,
            )
            return self._failure(agent, agent_input, budget_error, started_at, started)

        log.info(
            "agent_execution_started",
            provider=provider.name,
            model=model.id,
            routing_reason=reason,
            estimated_cost_usd=round(estimate, 6),
        )

        try:
            response = await asyncio.wait_for(
                provider.generate(request), timeout=agent.limits.timeout_seconds
            )
        except TimeoutError:
            log.warning("agent_execution_timed_out", timeout_seconds=agent.limits.timeout_seconds)
            return self._failure(
                agent,
                agent_input,
                ExecutionError(
                    kind=ErrorKind.TIMEOUT,
                    message=f"agent exceeded {agent.limits.timeout_seconds}s",
                    provider=provider.name,
                ),
                started_at,
                started,
                provider=provider.name,
                model=model.id,
                status=ExecutionStatus.TIMED_OUT,
            )
        except ProviderError as exc:
            log.warning(
                "provider_call_failed",
                provider=provider.name,
                model=model.id,
                error_kind=exc.kind.value,
                retryable=exc.is_retryable,
            )
            return self._failure(
                agent,
                agent_input,
                ExecutionError(
                    kind=exc.kind,
                    message=exc.message,
                    retryable=exc.is_retryable,
                    provider=exc.provider,
                ),
                started_at,
                started,
                provider=provider.name,
                model=model.id,
            )
        except asyncio.CancelledError:
            log.info("agent_execution_cancelled")
            raise

        return self._validate(agent, agent_input, response, model, started_at, started)

    # ---- internals ---------------------------------------------------------

    def _build_request(
        self, agent: AgentDefinition, agent_input: AgentInput, model: ModelSpec
    ) -> CompletionRequest:
        preference = agent.model_preference
        return CompletionRequest(
            model=model,
            system_prompt=build_system_prompt(agent),
            user_prompt=build_user_prompt(agent_input),
            max_output_tokens=min(preference.max_output_tokens, model.max_output_tokens),
            temperature=preference.temperature,
            response_schema=agent.output_schema,
            timeout_seconds=agent.limits.timeout_seconds,
        )

    @staticmethod
    def _check_budget(
        agent: AgentDefinition, context: ExecutionContext, estimate: float
    ) -> ExecutionError | None:
        if estimate > agent.limits.max_cost_usd:
            return ExecutionError(
                kind=ErrorKind.BUDGET_EXCEEDED,
                message=(
                    f"estimated cost ${estimate:.4f} exceeds the agent's limit of "
                    f"${agent.limits.max_cost_usd:.2f}"
                ),
                retryable=False,
                details={"estimated_cost_usd": estimate},
            )
        if context.remaining_budget_usd is not None and estimate > context.remaining_budget_usd:
            return ExecutionError(
                kind=ErrorKind.BUDGET_EXCEEDED,
                message=(
                    f"estimated cost ${estimate:.4f} exceeds the workflow's remaining "
                    f"budget of ${context.remaining_budget_usd:.4f}"
                ),
                retryable=False,
                details={"estimated_cost_usd": estimate},
            )
        return None

    def _validate(
        self,
        agent: AgentDefinition,
        agent_input: AgentInput,
        response: CompletionResponse,
        model: ModelSpec,
        started_at: datetime,
        started: float,
    ) -> AgentOutput:
        outcome = validate_agent_output(response.text, agent.output_schema)
        cost = model.cost_for(response.usage)
        latency_ms = (time.perf_counter() - started) * 1000
        bound = logger.bind(agent_id=agent.id, node_key=agent_input.node_key)

        if not outcome.valid:
            # Malformed output is a normal failure mode of a non-deterministic system.
            # It is retryable, and the raw text is preserved for debugging.
            bound.warning(
                "agent_output_invalid",
                provider=response.provider,
                model=model.id,
                validation_error=outcome.error,
                cost_usd=round(cost, 6),
            )
            return AgentOutput(
                agent_id=agent.id,
                node_key=agent_input.node_key,
                status=ExecutionStatus.INVALID_OUTPUT,
                payload=outcome.payload,
                provider=response.provider,
                model=model.id,
                usage=response.usage,
                cost_usd=cost,
                latency_ms=latency_ms,
                attempt=agent_input.attempt,
                error=ExecutionError(
                    kind=ErrorKind.INVALID_OUTPUT,
                    message=outcome.error or "output failed schema validation",
                    provider=response.provider,
                    details={"raw_output": response.text[:2_000]},
                ),
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )

        bound.info(
            "agent_execution_completed",
            provider=response.provider,
            model=model.id,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=round(cost, 6),
            latency_ms=round(latency_ms, 2),
            recovered_from_fence=outcome.recovered_from_fence,
        )
        return AgentOutput(
            agent_id=agent.id,
            node_key=agent_input.node_key,
            status=ExecutionStatus.SUCCEEDED,
            payload=outcome.payload,
            summary=_extract_summary(outcome.payload),
            provider=response.provider,
            model=model.id,
            usage=response.usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            attempt=agent_input.attempt,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )

    @staticmethod
    def _failure(
        agent: AgentDefinition,
        agent_input: AgentInput,
        error: ExecutionError,
        started_at: datetime,
        started: float,
        *,
        provider: str | None = None,
        model: str | None = None,
        status: ExecutionStatus = ExecutionStatus.FAILED,
    ) -> AgentOutput:
        if error.kind is ErrorKind.BUDGET_EXCEEDED:
            status = ExecutionStatus.BUDGET_EXCEEDED
        return AgentOutput(
            agent_id=agent.id,
            node_key=agent_input.node_key,
            status=status,
            provider=provider,
            model=model,
            usage=TokenUsage(),
            cost_usd=0.0,
            latency_ms=(time.perf_counter() - started) * 1000,
            attempt=agent_input.attempt,
            error=error,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )


def _can_fallback(output: AgentOutput) -> bool:
    """Whether another *provider* might succeed where this one did not.

    Authentication and malformed requests will fail the same way on every vendor of a
    given key. Unavailability, timeouts, and rate limits are properties of one vendor,
    so remaining models on that same adapter are skipped.
    """
    if output.error is None:
        return False
    return output.error.kind in {
        ErrorKind.PROVIDER_UNAVAILABLE,
        ErrorKind.TIMEOUT,
        ErrorKind.RATE_LIMITED,
    }


def _extract_summary(payload: dict[str, object]) -> str | None:
    """Pull a short human-readable line out of a payload, if the agent provided one."""
    for key in ("summary", "assessment", "rationale", "document"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return None
