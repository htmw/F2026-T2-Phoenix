"""Per-operator rate limits and soft rolling spend caps.

Rate counters live in Redis (or an in-process dict for tests). Spend is summed from
Postgres executions joined through workflow ``owner_id`` — Redis is never the ledger.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.identity import OperatorIdentity
from app.core.logging import get_logger
from app.models.workflow import ExecutionRecord, WorkflowNodeRecord, WorkflowRecord

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitVerdict:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    reset_at: int


@dataclass(frozen=True, slots=True)
class BudgetVerdict:
    allowed: bool
    spent_usd: float
    cap_usd: float | None
    window_hours: int


@dataclass(frozen=True, slots=True)
class AbuseStatus:
    rate: RateLimitVerdict
    budget: BudgetVerdict


class AbuseGuard:
    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
        *,
        redis: Any | None = None,
        memory: dict[str, Any] | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._redis = redis
        self._memory = memory if memory is not None else {}

    async def enforce(self, operator: OperatorIdentity) -> AbuseStatus:
        """Raise 429/402 when the operator is over limit; otherwise return status."""
        rate = await self.check_rate(operator.id)
        if not rate.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"rate limit exceeded for operator '{operator.id}': "
                    f"{rate.limit} requests per {self._settings.rate_limit_window_seconds}s"
                ),
                headers={
                    "Retry-After": str(rate.retry_after_seconds),
                    "X-RateLimit-Limit": str(rate.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(rate.reset_at),
                },
            )

        budget = await self.check_budget(operator.id)
        if not budget.allowed and budget.cap_usd is not None:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"operator budget exceeded: spent ${budget.spent_usd:.4f} of "
                    f"${budget.cap_usd:.4f} in the last {budget.window_hours}h"
                ),
                headers={
                    "X-Operator-Budget-Cap": f"{budget.cap_usd:.4f}",
                    "X-Operator-Budget-Spent": f"{budget.spent_usd:.4f}",
                },
            )

        return AbuseStatus(rate=rate, budget=budget)

    async def status(self, operator_id: str) -> AbuseStatus:
        """Read-only view (does not increment the rate counter)."""
        rate = await self.peek_rate(operator_id)
        budget = await self.check_budget(operator_id)
        return AbuseStatus(rate=rate, budget=budget)

    async def check_rate(self, operator_id: str) -> RateLimitVerdict:
        if not self._settings.rate_limit_enabled:
            return RateLimitVerdict(
                allowed=True,
                limit=self._settings.rate_limit_requests,
                remaining=self._settings.rate_limit_requests,
                retry_after_seconds=0,
                reset_at=int(time.time()) + self._settings.rate_limit_window_seconds,
            )
        if self._settings.rate_limit_backend == "memory" or self._redis is None:
            return self._memory_hit(operator_id)
        return await self._redis_hit(operator_id)

    async def peek_rate(self, operator_id: str) -> RateLimitVerdict:
        if not self._settings.rate_limit_enabled:
            return RateLimitVerdict(
                allowed=True,
                limit=self._settings.rate_limit_requests,
                remaining=self._settings.rate_limit_requests,
                retry_after_seconds=0,
                reset_at=int(time.time()) + self._settings.rate_limit_window_seconds,
            )
        if self._settings.rate_limit_backend == "memory" or self._redis is None:
            return self._memory_peek(operator_id)
        return await self._redis_peek(operator_id)

    async def check_budget(self, operator_id: str) -> BudgetVerdict:
        cap = self._settings.operator_budget_usd
        window = self._settings.operator_budget_window_hours
        if cap is None:
            return BudgetVerdict(allowed=True, spent_usd=0.0, cap_usd=None, window_hours=window)

        since = datetime.now(UTC) - timedelta(hours=window)
        statement = (
            select(func.coalesce(func.sum(ExecutionRecord.cost_usd), 0.0))
            .select_from(ExecutionRecord)
            .join(WorkflowNodeRecord, ExecutionRecord.node_id == WorkflowNodeRecord.id)
            .join(WorkflowRecord, WorkflowNodeRecord.workflow_id == WorkflowRecord.id)
            .where(
                WorkflowRecord.owner_id == operator_id,
                ExecutionRecord.created_at >= since,
            )
        )
        spent = float((await self._session.execute(statement)).scalar_one())
        return BudgetVerdict(
            allowed=spent < cap,
            spent_usd=round(spent, 6),
            cap_usd=cap,
            window_hours=window,
        )

    def _memory_hit(self, operator_id: str) -> RateLimitVerdict:
        key = f"rl:{operator_id}"
        now = time.time()
        window = self._settings.rate_limit_window_seconds
        limit = self._settings.rate_limit_requests
        entry = self._memory.get(key)
        if entry is None or now >= entry["reset_at"]:
            entry = {"count": 0, "reset_at": now + window}
            self._memory[key] = entry
        entry["count"] += 1
        remaining = max(0, limit - entry["count"])
        allowed = entry["count"] <= limit
        retry_after = max(1, int(entry["reset_at"] - now)) if not allowed else 0
        return RateLimitVerdict(
            allowed=allowed,
            limit=limit,
            remaining=remaining if allowed else 0,
            retry_after_seconds=retry_after,
            reset_at=int(entry["reset_at"]),
        )

    def _memory_peek(self, operator_id: str) -> RateLimitVerdict:
        key = f"rl:{operator_id}"
        now = time.time()
        window = self._settings.rate_limit_window_seconds
        limit = self._settings.rate_limit_requests
        entry = self._memory.get(key)
        if entry is None or now >= entry["reset_at"]:
            return RateLimitVerdict(
                allowed=True,
                limit=limit,
                remaining=limit,
                retry_after_seconds=0,
                reset_at=int(now + window),
            )
        remaining = max(0, limit - entry["count"])
        allowed = entry["count"] < limit
        return RateLimitVerdict(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            retry_after_seconds=max(1, int(entry["reset_at"] - now)) if not allowed else 0,
            reset_at=int(entry["reset_at"]),
        )

    async def _redis_hit(self, operator_id: str) -> RateLimitVerdict:
        if self._redis is None:
            raise ValueError("redis client required for redis rate-limit backend")
        key = f"agentorch:rl:{operator_id}"
        window = self._settings.rate_limit_window_seconds
        limit = self._settings.rate_limit_requests
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, window)
            ttl = await self._redis.ttl(key)
            if ttl < 0:
                ttl = window
                await self._redis.expire(key, window)
        except Exception:
            logger.warning("redis_rate_limit_failed", operator_id=operator_id)
            # Fail-open on Redis errors so a cache outage does not brick the office;
            # /readyz still reports Redis unhealthy separately.
            return RateLimitVerdict(
                allowed=True,
                limit=limit,
                remaining=limit,
                retry_after_seconds=0,
                reset_at=int(time.time()) + window,
            )
        remaining = max(0, limit - int(count))
        allowed = int(count) <= limit
        return RateLimitVerdict(
            allowed=allowed,
            limit=limit,
            remaining=remaining if allowed else 0,
            retry_after_seconds=int(ttl) if not allowed else 0,
            reset_at=int(time.time()) + max(int(ttl), 0),
        )

    async def _redis_peek(self, operator_id: str) -> RateLimitVerdict:
        if self._redis is None:
            raise ValueError("redis client required for redis rate-limit backend")
        key = f"agentorch:rl:{operator_id}"
        window = self._settings.rate_limit_window_seconds
        limit = self._settings.rate_limit_requests
        try:
            raw = await self._redis.get(key)
            ttl = await self._redis.ttl(key)
        except Exception:
            return RateLimitVerdict(
                allowed=True,
                limit=limit,
                remaining=limit,
                retry_after_seconds=0,
                reset_at=int(time.time()) + window,
            )
        count = int(raw) if raw is not None else 0
        if ttl < 0:
            ttl = window
        remaining = max(0, limit - count)
        allowed = count < limit
        return RateLimitVerdict(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            retry_after_seconds=int(ttl) if not allowed else 0,
            reset_at=int(time.time()) + max(int(ttl), 0),
        )
