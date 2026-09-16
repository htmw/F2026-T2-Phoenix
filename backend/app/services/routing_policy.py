"""Operator routing policy: provider priority order and blocked models."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider import RoutingPolicyRecord

POLICY_ID = "default"
_MAX_ENTRIES = 64


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """In-memory policy applied by ``ProviderRegistry.rank_models``."""

    provider_priority: tuple[str, ...] = ()
    blocked_models: frozenset[str] = frozenset()

    def provider_rank(self, provider_name: str) -> int:
        """Lower is better. Unlisted providers sort after every listed one."""
        try:
            return self.provider_priority.index(provider_name)
        except ValueError:
            return len(self.provider_priority) + 1

    def is_blocked(self, model_id: str) -> bool:
        return model_id in self.blocked_models


class RoutingPolicyView(BaseModel):
    provider_priority: list[str] = Field(default_factory=list)
    blocked_models: list[str] = Field(default_factory=list)


class RoutingPolicyUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_priority: list[str] = Field(default_factory=list, max_length=_MAX_ENTRIES)
    blocked_models: list[str] = Field(default_factory=list, max_length=_MAX_ENTRIES)

    @field_validator("provider_priority")
    @classmethod
    def _unique_providers(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("provider_priority must not contain duplicates")
        for item in cleaned:
            if len(item) > 32:
                raise ValueError(f"provider id too long: {item!r}")
        return cleaned

    @field_validator("blocked_models")
    @classmethod
    def _valid_model_ids(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("blocked_models must not contain duplicates")
        for item in cleaned:
            if len(item) > 128:
                raise ValueError(f"model id too long: {item!r}")
            if ":" not in item:
                raise ValueError(f"blocked model id must be provider:name, got {item!r}")
        return cleaned


def policy_from_record(record: RoutingPolicyRecord | None) -> RoutingPolicy:
    if record is None:
        return RoutingPolicy()
    return RoutingPolicy(
        provider_priority=tuple(record.provider_priority or ()),
        blocked_models=frozenset(record.blocked_models or ()),
    )


def view_from_policy(policy: RoutingPolicy) -> RoutingPolicyView:
    return RoutingPolicyView(
        provider_priority=list(policy.provider_priority),
        blocked_models=sorted(policy.blocked_models),
    )


async def get_policy(session: AsyncSession) -> RoutingPolicy:
    record = await session.get(RoutingPolicyRecord, POLICY_ID)
    return policy_from_record(record)


async def get_or_create_record(session: AsyncSession) -> RoutingPolicyRecord:
    record = await session.get(RoutingPolicyRecord, POLICY_ID)
    if record is None:
        record = RoutingPolicyRecord(id=POLICY_ID, provider_priority=[], blocked_models=[])
        session.add(record)
        await session.flush()
    return record


async def update_policy(session: AsyncSession, body: RoutingPolicyUpdate) -> RoutingPolicy:
    record = await get_or_create_record(session)
    record.provider_priority = list(body.provider_priority)
    record.blocked_models = list(body.blocked_models)
    await session.flush()
    return policy_from_record(record)
