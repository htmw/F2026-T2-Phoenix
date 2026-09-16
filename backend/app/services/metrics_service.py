"""Durable answers to operator questions about cost and reliability.

The five questions this product has to answer without a spreadsheet: what did workflows
cost, which agent was slowest, how often did we retry, which provider is failing, and
how many tokens did we spend. All of that is already on ``executions``; this module
aggregates it.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ExecutionStatus
from app.models.workflow import ExecutionRecord, WorkflowNodeRecord, WorkflowRecord


class MetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self) -> dict[str, object]:
        totals = await self._session.execute(
            select(
                func.coalesce(func.sum(ExecutionRecord.cost_usd), 0.0),
                func.coalesce(func.sum(ExecutionRecord.input_tokens), 0),
                func.coalesce(func.sum(ExecutionRecord.output_tokens), 0),
                func.count(ExecutionRecord.id),
            )
        )
        cost, input_tokens, output_tokens, attempts = totals.one()

        workflow_count = await self._session.scalar(select(func.count(WorkflowRecord.id))) or 0

        slowest_row = (
            await self._session.execute(
                select(
                    WorkflowNodeRecord.agent_id,
                    WorkflowNodeRecord.node_key,
                    ExecutionRecord.latency_ms,
                    WorkflowNodeRecord.workflow_id,
                    ExecutionRecord.provider_id,
                    ExecutionRecord.model_id,
                )
                .join(WorkflowNodeRecord, ExecutionRecord.node_id == WorkflowNodeRecord.id)
                .order_by(ExecutionRecord.latency_ms.desc())
                .limit(1)
            )
        ).first()

        retry_rows = (
            await self._session.execute(
                select(WorkflowNodeRecord.agent_id, func.count(ExecutionRecord.id))
                .join(WorkflowNodeRecord, ExecutionRecord.node_id == WorkflowNodeRecord.id)
                .where(ExecutionRecord.attempt > 1)
                .group_by(WorkflowNodeRecord.agent_id)
            )
        ).all()

        failing_rows = (
            await self._session.execute(
                select(ExecutionRecord.provider_id, func.count(ExecutionRecord.id))
                .where(
                    ExecutionRecord.status != ExecutionStatus.SUCCEEDED,
                    ExecutionRecord.provider_id.is_not(None),
                )
                .group_by(ExecutionRecord.provider_id)
            )
        ).all()

        slowest: dict[str, object] | None = None
        if slowest_row is not None:
            slowest = {
                "agent_id": slowest_row.agent_id,
                "node_key": slowest_row.node_key,
                "latency_ms": float(slowest_row.latency_ms),
                "workflow_id": str(slowest_row.workflow_id),
                "provider": slowest_row.provider_id,
                "model": slowest_row.model_id,
            }

        return {
            "workflow_count": int(workflow_count),
            "attempt_count": int(attempts),
            "total_cost_usd": round(float(cost), 6),
            "token_totals": {
                "input": int(input_tokens),
                "output": int(output_tokens),
                "total": int(input_tokens) + int(output_tokens),
            },
            "slowest_agent": slowest,
            "retry_counts": {agent_id: int(count) for agent_id, count in retry_rows},
            "failing_providers": {
                provider: int(count) for provider, count in failing_rows if provider
            },
        }
