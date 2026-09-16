"""Encrypted operator-managed provider API keys.

Keys accepted through Settings are stored encrypted at rest. They are never returned
in API responses — only a masked hint (last four characters) is exposed.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import ProviderConnectionStatus
from app.models.provider import ProviderConnectionRecord

logger = get_logger(__name__)


def mask_api_key(api_key: str) -> str:
    """Return a display hint that never includes the full secret."""
    cleaned = api_key.strip()
    if len(cleaned) <= 4:
        return "••••"
    return f"••••{cleaned[-4:]}"


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key(settings)).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(settings: Settings, ciphertext: str) -> str:
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key(settings)).decrypt(ciphertext.encode("ascii")).decode("utf-8")


def _fernet_key(settings: Settings) -> bytes:
    """Derive a Fernet key from ENCRYPTION_KEY (or a documented dev fallback)."""
    raw = (
        settings.encryption_key.get_secret_value()
        if settings.encryption_key is not None
        else None
    )
    if not raw:
        if settings.is_production:
            raise RuntimeError("ENCRYPTION_KEY is required in production")
        raw = f"dev-only::{settings.database_url}"
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


async def load_connection_secrets(
    session: AsyncSession, settings: Settings
) -> dict[str, str]:
    """Decrypt stored keys for registry construction. Never log the values."""
    rows = (await session.execute(select(ProviderConnectionRecord))).scalars().all()
    secrets: dict[str, str] = {}
    for row in rows:
        if row.status == ProviderConnectionStatus.DISCONNECTED.value:
            continue
        try:
            secrets[row.provider_id] = decrypt_secret(settings, row.encrypted_api_key)
        except Exception as exc:  # noqa: BLE001 — corrupt ciphertext must not crash startup
            logger.warning(
                "provider_secret_decrypt_failed",
                provider_id=row.provider_id,
                error=type(exc).__name__,
            )
            continue
    return secrets


async def get_connection(
    session: AsyncSession, provider_id: str
) -> ProviderConnectionRecord | None:
    return await session.get(ProviderConnectionRecord, provider_id)


async def upsert_connection(
    session: AsyncSession,
    settings: Settings,
    *,
    provider_id: str,
    api_key: str,
    status: ProviderConnectionStatus = ProviderConnectionStatus.CONNECTED,
    discovered_models: list[str] | None = None,
    last_error: str | None = None,
) -> ProviderConnectionRecord:
    row = await get_connection(session, provider_id)
    if row is None:
        row = ProviderConnectionRecord(provider_id=provider_id)
        session.add(row)
    row.encrypted_api_key = encrypt_secret(settings, api_key.strip())
    row.key_hint = mask_api_key(api_key)
    row.auth_method = "api_key"
    row.status = status.value
    row.last_error = last_error
    row.last_verified_at = (
        datetime.now(UTC) if status is ProviderConnectionStatus.CONNECTED else None
    )
    if discovered_models is not None:
        row.discovered_models = list(discovered_models)
    await session.flush()
    return row


async def mark_connection(
    session: AsyncSession,
    provider_id: str,
    *,
    status: ProviderConnectionStatus,
    last_error: str | None = None,
    discovered_models: list[str] | None = None,
) -> ProviderConnectionRecord | None:
    row = await get_connection(session, provider_id)
    if row is None:
        return None
    row.status = status.value
    row.last_error = last_error
    if status is ProviderConnectionStatus.CONNECTED:
        row.last_verified_at = datetime.now(UTC)
    if discovered_models is not None:
        row.discovered_models = list(discovered_models)
    await session.flush()
    return row


async def delete_connection(session: AsyncSession, provider_id: str) -> bool:
    row = await get_connection(session, provider_id)
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def list_connections(session: AsyncSession) -> list[ProviderConnectionRecord]:
    result = await session.execute(select(ProviderConnectionRecord))
    return list(result.scalars().all())
