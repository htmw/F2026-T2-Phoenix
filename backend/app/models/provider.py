"""Provider catalogue and encrypted connection records.

Pricing/catalogue rows live in ``providers`` / ``models``. Operator API keys live in
``provider_connections`` as ciphertext only — never plaintext.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.domain.enums import ProviderConnectionStatus


class ProviderRecord(Base, TimestampMixin):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    models: Mapped[list[ModelRecord]] = relationship(
        back_populates="provider", cascade="all, delete-orphan", lazy="selectin"
    )


class ModelRecord(Base, TimestampMixin):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    traits: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    context_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=8_000)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4_096)
    input_cost_per_million: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_cost_per_million: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    typical_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=2_000)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    provider: Mapped[ProviderRecord] = relationship(back_populates="models")


class ProviderConnectionRecord(Base, TimestampMixin):
    __tablename__ = "provider_connections"

    provider_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_hint: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    auth_method: Mapped[str] = mapped_column(String(32), nullable=False, default="api_key")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProviderConnectionStatus.CONNECTED.value
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    discovered_models: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class RoutingPolicyRecord(Base, TimestampMixin):
    """Singleton operator routing policy (provider order + blocked model ids)."""

    __tablename__ = "routing_policy"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    provider_priority: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    blocked_models: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
