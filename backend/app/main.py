"""Application entry point.

``create_app`` is a factory rather than a module-level singleton so tests can build an
app with alternative settings, and so import of this module has no side effects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.agents.builtin import BUILTIN_AGENTS
from app.agents.seed import seed_agents
from app.api.middleware import RequestContextMiddleware
from app.api.routes import agents, capabilities, health, metrics, network, providers, runs, tasks
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.redis_client import close_redis, create_redis
from app.database.session import create_engine, create_session_factory, session_scope
from app.providers.registry import build_provider_registry

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.rate_limit_memory = {}
        app.state.redis = await create_redis(settings)

        # Log which providers are configured by name only -- never key material -- so
        # operators can diagnose "why was this provider unavailable" from the logs.
        logger.info(
            "application_starting",
            app=settings.app_name,
            environment=settings.environment,
            configured_providers=settings.configured_providers(),
            rate_limit_backend=settings.rate_limit_backend,
            rate_limit_enabled=settings.rate_limit_enabled,
        )

        if settings.seed_agents_on_startup:
            # Seeding must not stop the API from serving: a database that is briefly
            # unavailable should degrade readiness, not prevent startup entirely.
            try:
                async with session_scope(session_factory) as session:
                    await seed_agents(session, BUILTIN_AGENTS)
            except Exception:
                logger.exception("agent_seeding_failed")

        # Overlay Settings-stored provider keys and routing policy onto the registry.
        try:
            async with session_scope(session_factory) as session:
                from app.providers.registry import build_provider_registry
                from app.services.provider_connections import load_connection_secrets
                from app.services.routing_policy import get_policy

                overrides = await load_connection_secrets(session, settings)
                policy = await get_policy(session)
                app.state.provider_registry = build_provider_registry(
                    settings, credential_overrides=overrides, policy=policy
                )
        except Exception:
            logger.exception("provider_connection_load_failed")

        try:
            yield
        finally:
            # In-flight workflows are abandoned rather than awaited: a deploy should not
            # wait minutes for a run. Their state is committed per batch, so they remain
            # resumable records rather than lost work.
            runner = getattr(app.state, "workflow_runner", None)
            if runner is not None:
                await runner.shutdown()
            await close_redis(getattr(app.state, "redis", None))
            await engine.dispose()
            logger.info("application_stopped")

    app = FastAPI(
        title=settings.app_name,
        description="Orchestration engine for specialised AI agents.",
        version="0.2.0",
        lifespan=lifespan,
        # Interactive docs are useful in development but are an information leak in
        # production, where the schema should be published deliberately instead.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    if settings.is_production:
        # Starlette matches the Host header against this list. Applied only in
        # production so local/dev hostnames stay flexible.
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        if settings.is_production
        else ["*"],
        allow_headers=["Authorization", "Content-Type", "X-Operator-Id", "X-Request-ID"]
        if settings.is_production
        else ["*"],
    )

    # Probes stay unversioned at the root; domain endpoints are versioned.
    app.include_router(health.router)
    app.include_router(metrics.scrape_router)

    v1 = APIRouter(prefix=settings.api_v1_prefix)
    v1.include_router(agents.router)
    v1.include_router(capabilities.router)
    v1.include_router(providers.router)
    v1.include_router(runs.router)
    v1.include_router(tasks.router)
    v1.include_router(metrics.api_router)
    v1.include_router(network.router)
    app.include_router(v1)

    app.state.settings = settings
    app.state.rate_limit_memory = {}
    app.state.redis = None
    # Provider adapters are stateless and their configuration cannot change mid-process,
    # so the registry is built once here rather than per request or in lifespan.
    app.state.provider_registry = build_provider_registry(settings)
    return app


app = create_app()
