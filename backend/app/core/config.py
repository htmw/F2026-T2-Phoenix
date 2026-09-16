"""Application configuration.

All configuration enters the process here and nowhere else. Business logic reads a
``Settings`` instance rather than the environment, which keeps configuration out of the
domain and makes tests able to construct alternative settings without patching os.environ.

Provider credentials are held as ``SecretStr`` so that repr/str, log rendering, and
accidental model serialisation emit ``**********`` instead of the key.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
AuthMode = Literal["off", "header"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repo root first, then cwd, so tools run from backend/ (alembic, pytest) read
        # the same .env as a process started from the repo root. Later files win.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_name: str = "AI Agent Orchestration Platform"
    environment: Environment = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # ---- Auth foundations (Universal Office Sprint 9) ----
    # ``off`` — resolve a default operator (dev/tests); still stamps ownership.
    # ``header`` — require X-Operator-Id or Bearer; JWT validation replaces Bearer later.
    # Production forbids ``off`` (see ``_production_invariants``).
    auth_mode: AuthMode = "header"
    # Used when auth_mode=off and no identity header is present.
    dev_operator_id: str = "operator"

    # ---- Abuse protection (Universal Office Sprint 10) ----
    # Per-operator request rate on mutating routes. ``memory`` is for hermetic tests.
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["redis", "memory"] = "redis"
    rate_limit_requests: int = Field(default=60, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    # Soft rolling spend cap across an operator's workflows. None = unlimited.
    operator_budget_usd: float | None = Field(default=None, gt=0, le=1_000_000)
    operator_budget_window_hours: int = Field(default=24, ge=1, le=168)

    # ---- Logging ----
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    # ---- Dependencies ----
    database_url: str = "postgresql+asyncpg://agentorch:agentorch@localhost:5432/agentorch"
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=50)
    redis_url: str = "redis://localhost:6379/0"

    # ---- Agent registry ----
    # Re-seed built-in agent definitions at startup. Safe by default because seeding is
    # an idempotent upsert; disable in production (enforced) so the registry changes only
    # by deliberate migration.
    seed_agents_on_startup: bool = True

    # ---- Orchestration ----
    # Use a model to decide which capabilities a request needs. Falls back to
    # heuristics automatically on any failure; set false to avoid the extra call.
    use_llm_capability_analysis: bool = True
    # Upper bound on agents executing at once within one workflow. Bounded so a wide
    # workflow cannot exhaust provider connections or trip a rate limit that would fail
    # every branch together.
    max_parallel_agents: int = Field(default=4, ge=1, le=32)
    # How many times a downstream verdict may send work back upstream. A coding agent
    # and a testing agent can disagree indefinitely, and each round costs money.
    max_repair_cycles: int = Field(default=1, ge=0, le=5)

    # ---- HTTP ----
    # NoDecode disables pydantic-settings' automatic JSON decoding of complex types.
    # Without it, a plain `CORS_ALLOW_ORIGINS=http://localhost:3000` is rejected as
    # malformed JSON before the validator below ever runs.
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    # Host header allow-list for TrustedHostMiddleware (production).
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )

    # ---- Provider credentials (backend only; never exposed to clients) ----
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    xai_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    mistral_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    moonshot_api_key: SecretStr | None = None
    cohere_api_key: SecretStr | None = None
    perplexity_api_key: SecretStr | None = None
    together_api_key: SecretStr | None = None
    qwen_api_key: SecretStr | None = None

    # Symmetric key for encrypting Settings-managed provider credentials at rest.
    # Required in production. Development falls back to a derived key (see service).
    encryption_key: SecretStr | None = None

    # HS256 secret for validating Authorization: Bearer JWTs (``sub`` = operator id).
    # Required in production. Dev/UI can rely on X-Operator-Id without a JWT.
    jwt_secret: SecretStr | None = None
    jwt_audience: str | None = None
    jwt_issuer: str | None = None

    @field_validator("cors_allow_origins", "allowed_hosts", mode="before")
    @classmethod
    def _split_csv_list(cls, value: object) -> object:
        """Accept a comma-separated string so `.env` files stay readable."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _production_invariants(self) -> Settings:
        """Fail fast on misconfigured production rather than serving insecure defaults."""
        if not self.is_production:
            return self

        errors: list[str] = []
        if self.auth_mode == "off":
            errors.append("AUTH_MODE=off is forbidden in production (use header)")
        if self.debug:
            errors.append("DEBUG must be false in production")
        if self.seed_agents_on_startup:
            errors.append("SEED_AGENTS_ON_STARTUP must be false in production")
        key = (
            self.encryption_key.get_secret_value()
            if self.encryption_key is not None
            else ""
        )
        if not key.strip():
            errors.append("ENCRYPTION_KEY is required in production")
        jwt = (
            self.jwt_secret.get_secret_value() if self.jwt_secret is not None else ""
        )
        if not jwt.strip():
            errors.append("JWT_SECRET is required in production")
        if not self.cors_allow_origins:
            errors.append("CORS_ALLOW_ORIGINS must list at least one origin in production")
        if any(origin.strip() == "*" for origin in self.cors_allow_origins):
            errors.append("CORS_ALLOW_ORIGINS must not include '*' in production")
        if not self.allowed_hosts:
            errors.append("ALLOWED_HOSTS must list at least one host in production")
        if any(host.strip() == "*" for host in self.allowed_hosts):
            errors.append("ALLOWED_HOSTS must not include '*' in production")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def configured_providers(self) -> list[str]:
        """Names of providers that have a credential present.

        Reports *which* providers are usable without revealing any key material, so
        startup logs and operator tooling can show configuration state safely.
        """
        candidates = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
            "xai": self.xai_api_key,
            "deepseek": self.deepseek_api_key,
            "mistral": self.mistral_api_key,
            "openrouter": self.openrouter_api_key,
        }
        return sorted(name for name, key in candidates.items() if key and key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
