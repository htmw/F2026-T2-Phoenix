"""Google session login and cross-user isolation for memory and files."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import get_session
from app.core.config import Settings
from app.core.google_auth import decode_google_id_token
from app.main import create_app


def _rsa_pair() -> tuple[bytes, object]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private, key.public_key()


def _id_token(private: bytes, *, sub: str, email: str, client_id: str = "test-client") -> str:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": client_id,
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": "Test User",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private,
        algorithm="RS256",
    )
    return token if isinstance(token, str) else token.decode()


def test_google_id_token_rejects_unverified_email() -> None:
    private, public = _rsa_pair()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": "test-client",
            "sub": "111",
            "email": "a@example.com",
            "email_verified": False,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private,
        algorithm="RS256",
    )
    with pytest.raises(Exception, match="not verified"):
        decode_google_id_token(
            token if isinstance(token, str) else token.decode(),
            client_id="test-client",
            key=public,
        )


@pytest.fixture
def google_settings() -> Settings:
    return Settings(
        environment="test",
        auth_mode="google",
        google_client_id="test-client",
        jwt_secret="test-session-secret",
        database_url="postgresql+asyncpg://agentorch:change-me-locally@localhost:5432/agentorch_test",
        redis_url="redis://localhost:6379/15",
        seed_agents_on_startup=False,
        use_llm_capability_analysis=False,
        rate_limit_backend="memory",
        rate_limit_enabled=True,
        rate_limit_requests=10_000,
        dev_operator_id="operator",
        log_level="WARNING",
        _env_file=None,
    )


async def test_google_login_and_memory_isolation(
    google_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    private, public = _rsa_pair()
    app = create_app(google_settings)
    app.state.google_token_key = public
    app.state.session_factory = session_factory

    async def override_session():  # type: ignore[no-untyped-def]
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        alice_token = _id_token(private, sub="111222333", email="alice@example.com")
        bob_token = _id_token(private, sub="444555666", email="bob@example.com")
        alice = await client.post("/api/v1/auth/google", json={"id_token": alice_token})
        bob = await client.post("/api/v1/auth/google", json={"id_token": bob_token})
        assert alice.status_code == 200, alice.text
        assert bob.status_code == 200, bob.text
        alice_session = alice.json()["session_token"]
        bob_session = bob.json()["session_token"]

        saved = await client.post(
            "/api/v1/memory",
            headers={"Authorization": f"Bearer {alice_session}"},
            json={
                "visibility": "operator",
                "title": "Preference",
                "content": {"fact": "Alice prefers morning reviews"},
            },
        )
        assert saved.status_code == 201, saved.text

        bob_view = await client.get(
            "/api/v1/memory/mine",
            headers={"Authorization": f"Bearer {bob_session}"},
        )
        assert bob_view.status_code == 200
        assert bob_view.json() == []

        made = await client.post(
            "/api/v1/files",
            headers={"Authorization": f"Bearer {alice_session}"},
            json={"title": "Board report", "body": "Revenue grew.", "file_format": "pdf"},
        )
        assert made.status_code == 201, made.text
        file_id = made.json()["id"]
        stolen = await client.get(
            f"/api/v1/files/{file_id}",
            headers={"Authorization": f"Bearer {bob_session}"},
        )
        assert stolen.status_code == 404
        own = await client.get(
            f"/api/v1/files/{file_id}",
            headers={"Authorization": f"Bearer {alice_session}"},
        )
        assert own.status_code == 200
        assert own.content.startswith(b"%PDF-")

        clash = await client.post(
            "/api/v1/auth/google",
            json={
                "id_token": _id_token(private, sub="999888777", email="alice@example.com"),
            },
        )
        assert clash.status_code == 409
