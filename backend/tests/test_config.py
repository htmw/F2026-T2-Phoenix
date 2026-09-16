"""Configuration and secret-handling tests.

The secret assertions are the executable form of the rule that provider keys must never
leave the backend. They are cheap now and they fail loudly if someone later adds a
settings dump to an endpoint or a log line.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_cors_origins_accept_comma_separated_string() -> None:
    settings = make_settings(cors_allow_origins="http://a.test, http://b.test")

    assert settings.cors_allow_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_are_read_from_a_plain_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Goes through the environment source rather than the constructor: settings loaded
    # from env take a different code path, and a JSON-only list decoder crashes the
    # process here while passing a constructor-based test.
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a.test,http://b.test")

    settings = make_settings()

    assert settings.cors_allow_origins == ["http://a.test", "http://b.test"]


def test_single_cors_origin_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")

    assert make_settings().cors_allow_origins == ["http://localhost:3000"]


def test_settings_load_from_environment_like_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("AUTH_MODE", "header")
    monkeypatch.setenv("SEED_AGENTS_ON_STARTUP", "false")
    monkeypatch.setenv("ENCRYPTION_KEY", "prod-test-encryption-key-value")
    monkeypatch.setenv("JWT_SECRET", "prod-test-jwt-secret-value")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://office.example")
    monkeypatch.setenv("ALLOWED_HOSTS", "office.example,api.office.example")

    settings = make_settings()

    assert settings.is_production is True
    assert settings.log_format == "json"
    assert settings.redis_url == "redis://redis:6379/0"
    assert settings.auth_mode == "header"
    assert settings.seed_agents_on_startup is False
    assert settings.cors_allow_origins == ["https://office.example"]
    assert settings.allowed_hosts == ["office.example", "api.office.example"]
    assert settings.jwt_secret is not None


def test_invalid_environment_fails_fast() -> None:
    with pytest.raises(ValidationError):
        make_settings(environment="staging-ish")


def test_configured_providers_lists_only_providers_with_keys() -> None:
    settings = make_settings(openai_api_key="sk-test", anthropic_api_key="")

    assert settings.configured_providers() == ["openai"]


def test_api_keys_are_not_revealed_by_string_conversion() -> None:
    settings = make_settings(openai_api_key="sk-super-secret")

    assert "sk-super-secret" not in str(settings)
    assert "sk-super-secret" not in repr(settings)


def test_api_keys_are_not_revealed_by_serialisation() -> None:
    settings = make_settings(openai_api_key="sk-super-secret")

    dumped = json.dumps(settings.model_dump(mode="json"))

    assert "sk-super-secret" not in dumped


def test_api_key_is_readable_only_through_explicit_unwrap() -> None:
    settings = make_settings(openai_api_key="sk-super-secret")

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-super-secret"
