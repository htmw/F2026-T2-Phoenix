"""Production settings fail-fast guards (Universal Office Sprint 11)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def _prod(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "production",
        "auth_mode": "header",
        "debug": False,
        "seed_agents_on_startup": False,
        "encryption_key": "prod-encryption-key-for-tests",
        "jwt_secret": "prod-jwt-secret-for-tests",
        "cors_allow_origins": ["https://office.example"],
        "allowed_hosts": ["office.example", "api.office.example"],
        "log_format": "json",
    }
    base.update(overrides)
    return make_settings(**base)


def test_production_accepts_hardened_settings() -> None:
    settings = _prod()
    assert settings.is_production
    assert settings.auth_mode == "header"
    assert settings.seed_agents_on_startup is False


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"auth_mode": "off"}, "AUTH_MODE=off"),
        ({"debug": True}, "DEBUG must be false"),
        ({"seed_agents_on_startup": True}, "SEED_AGENTS_ON_STARTUP"),
        ({"encryption_key": None}, "ENCRYPTION_KEY"),
        ({"encryption_key": "   "}, "ENCRYPTION_KEY"),
        ({"jwt_secret": None}, "JWT_SECRET"),
        ({"jwt_secret": "   "}, "JWT_SECRET"),
        ({"cors_allow_origins": []}, "CORS_ALLOW_ORIGINS must list"),
        ({"cors_allow_origins": ["*"]}, "must not include '*'"),
        ({"allowed_hosts": []}, "ALLOWED_HOSTS must list"),
        ({"allowed_hosts": ["*"]}, "ALLOWED_HOSTS must not include"),
    ],
)
def test_production_rejects_insecure_defaults(
    overrides: dict[str, object], needle: str
) -> None:
    with pytest.raises(ValidationError) as exc:
        _prod(**overrides)
    assert needle in str(exc.value)


def test_non_production_still_allows_auth_off() -> None:
    settings = make_settings(environment="development", auth_mode="off", debug=True)
    assert settings.auth_mode == "off"
    assert settings.debug is True


def test_create_app_adds_trusted_host_in_production() -> None:
    app = create_app(_prod())
    names = [middleware.cls.__name__ for middleware in app.user_middleware]
    assert "TrustedHostMiddleware" in names


def test_create_app_skips_trusted_host_outside_production() -> None:
    app = create_app(make_settings(environment="test", auth_mode="off"))
    names = [middleware.cls.__name__ for middleware in app.user_middleware]
    assert "TrustedHostMiddleware" not in names
