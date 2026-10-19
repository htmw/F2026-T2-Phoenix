"""Agent registry tables.

Agents are rows, not code branches. ``agent_capabilities`` is a separate table rather
than a JSON array because selecting agents by capability is the orchestrator's hottest
query and needs an index.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class AgentRecord(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    model_preference: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    retry_policy: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=120.0)
    max_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Models the enrolling engineer declared the agent works with; empty means any.
    supported_models: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Per-agent result table in the ``agent_data`` schema, built from ``output_schema``.
    table_name: Mapped[str | None] = mapped_column(String(63), nullable=True)

    capabilities: Mapped[list[AgentCapabilityRecord]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        lazy="selectin",  # registry loads always need capabilities; avoids N+1
    )


# Names are what people type and read, so "Data Cleaner" and "data cleaner" are the same
# agent; enforced in the database so concurrent enrollments cannot both win.
Index("uq_agents_name_lower", func.lower(AgentRecord.name), unique=True)


class AgentCapabilityRecord(Base):
    __tablename__ = "agent_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    capability: Mapped[str] = mapped_column(String(64), nullable=False)

    agent: Mapped[AgentRecord] = relationship(back_populates="capabilities")

    __table_args__ = (
        Index("ix_agent_capabilities_capability", "capability"),
        Index("uq_agent_capability", "agent_id", "capability", unique=True),
    )
