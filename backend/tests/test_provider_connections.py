"""Provider connection encryption and Settings management APIs."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.enums import ProviderConnectionStatus
from app.services import provider_connections as connections
from app.services import provider_management as management


def test_mask_api_key_hides_the_secret() -> None:
    assert connections.mask_api_key("sk-abcdefghijklmnop") == "••••mnop"
    assert "sk-" not in connections.mask_api_key("sk-abcdefghijklmnop")


def test_encrypt_round_trip(settings: Settings) -> None:
    token = connections.encrypt_secret(settings, "sk-test-secret-value")
    assert "sk-test" not in token
    assert connections.decrypt_secret(settings, token) == "sk-test-secret-value"


async def test_list_providers_includes_disconnected_catalogue(
    db_client: AsyncClient,
) -> None:
    response = await db_client.get("/api/v1/providers")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body}
    assert {"openai", "anthropic", "google", "deepseek", "xai", "mistral", "openrouter"} <= names
    openai = next(item for item in body if item["name"] == "openai")
    assert openai["configured"] is False
    assert openai["connection_status"] == "disconnected"
    assert openai["auth_method"] == "api_key"
    assert "api_key" not in str(body).lower() or all(
        "sk-" not in str(item.get("key_hint") or "") for item in body
    )


async def test_connect_requires_successful_auth(
    db_client: AsyncClient, monkeypatch: object
) -> None:
    async def fail(_provider_id: str, _api_key: str):
        return ProviderConnectionStatus.AUTH_FAILED, [], "invalid api key sk-leak"

    monkeypatch.setattr(management, "test_provider_key", fail)  # type: ignore[arg-type]
    response = await db_client.post(
        "/api/v1/providers/openai/connect",
        json={"api_key": "sk-definitely-fake-key"},
    )
    assert response.status_code == 400
    assert "sk-leak" not in response.text
    assert "sk-definitely" not in response.text


async def test_connect_persists_masked_credential(
    db_client: AsyncClient, seeded_session: AsyncSession, settings: Settings, monkeypatch: object
) -> None:
    async def ok(_provider_id: str, _api_key: str):
        return ProviderConnectionStatus.CONNECTED, ["gpt-4o", "gpt-4o-mini"], None

    monkeypatch.setattr(management, "test_provider_key", ok)  # type: ignore[arg-type]
    response = await db_client.post(
        "/api/v1/providers/openai/connect",
        json={"api_key": "sk-test-openai-secret-9999"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"]["configured"] is True
    assert body["provider"]["key_hint"] == "••••9999"
    assert "sk-test-openai-secret" not in response.text
    assert "gpt-4o" in body["provider"]["discovered_models"]

    row = await connections.get_connection(seeded_session, "openai")
    assert row is not None
    assert connections.decrypt_secret(settings, row.encrypted_api_key).endswith("9999")


async def test_disconnect_removes_settings_credential(
    db_client: AsyncClient, monkeypatch: object
) -> None:
    async def ok(_provider_id: str, _api_key: str):
        return ProviderConnectionStatus.CONNECTED, ["gpt-4o"], None

    monkeypatch.setattr(management, "test_provider_key", ok)  # type: ignore[arg-type]
    await db_client.post(
        "/api/v1/providers/anthropic/connect",
        json={"api_key": "sk-ant-test-key-1234"},
    )
    response = await db_client.delete("/api/v1/providers/anthropic/disconnect")
    assert response.status_code == 200
    assert response.json()["provider"]["connection_status"] == "disconnected"
