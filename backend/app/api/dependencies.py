"""Shared FastAPI dependencies.

Settings and infrastructure are resolved from ``app.state`` rather than from module
globals. Without this, an app built by ``create_app`` with explicit settings would still
serve requests using process-wide environment settings — the injected configuration
would be silently ignored.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.registry import AgentRegistry, DatabaseAgentRegistry
from app.core.config import Settings
from app.core.identity import OperatorIdentity, resolve_operator
from app.core.redis_client import memory_store_from_request, redis_from_request
from app.orchestration.capability_analysis import CapabilityAnalyser
from app.providers.registry import ProviderRegistry
from app.services.abuse_limits import AbuseGuard, AbuseStatus
from app.services.agent_executor import AgentExecutor
from app.services.factory import (
    build_capability_analyser,
    build_engine,
    build_orchestration_service,
)
from app.services.orchestration_service import OrchestrationService
from app.services.single_agent_service import SingleAgentService
from app.services.workflow_repository import WorkflowRepository
from app.services.workflow_runner import WorkflowRunner
from app.workflows.engine import WorkflowEngine


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


async def get_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[AsyncSession]:
    """Provide a request-scoped session that commits on success.

    Committing here rather than in each route keeps a request's writes atomic: a handler
    that fails halfway through leaves no partial workflow behind.
    """
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_operator(request: Request, settings: SettingsDep) -> OperatorIdentity:
    """Resolve the calling operator (JWT ``sub`` slot later)."""
    identity = resolve_operator(request, settings)
    request.state.operator_id = identity.id
    return identity


OperatorDep = Annotated[OperatorIdentity, Depends(get_operator)]


async def enforce_abuse_limits(
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
    operator: OperatorDep,
) -> AbuseStatus:
    """Rate-limit and soft-budget gate for mutating routes."""
    guard = AbuseGuard(
        settings,
        session,
        redis=redis_from_request(request),
        memory=memory_store_from_request(request),
    )
    return await guard.enforce(operator)


AbuseGuardDep = Annotated[AbuseStatus, Depends(enforce_abuse_limits)]


async def get_abuse_status(
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
    operator: OperatorDep,
) -> AbuseStatus:
    guard = AbuseGuard(
        settings,
        session,
        redis=redis_from_request(request),
        memory=memory_store_from_request(request),
    )
    return await guard.status(operator.id)


AbuseStatusDep = Annotated[AbuseStatus, Depends(get_abuse_status)]


def get_registry(session: SessionDep) -> AgentRegistry:
    return DatabaseAgentRegistry(session)


RegistryDep = Annotated[AgentRegistry, Depends(get_registry)]


def get_provider_registry(request: Request) -> ProviderRegistry:
    """The provider registry is built once at startup, not per request.

    Adapters hold connection pools and their configuration cannot change mid-process,
    so rebuilding per request would only add latency.
    """
    registry: ProviderRegistry = request.app.state.provider_registry
    return registry


ProviderRegistryDep = Annotated[ProviderRegistry, Depends(get_provider_registry)]


def get_repository(session: SessionDep) -> WorkflowRepository:
    return WorkflowRepository(session)


RepositoryDep = Annotated[WorkflowRepository, Depends(get_repository)]


def get_executor(providers: ProviderRegistryDep) -> AgentExecutor:
    return AgentExecutor(providers)


ExecutorDep = Annotated[AgentExecutor, Depends(get_executor)]


def get_single_agent_service(
    registry: RegistryDep, executor: ExecutorDep, repository: RepositoryDep
) -> SingleAgentService:
    return SingleAgentService(registry, executor, repository)


SingleAgentServiceDep = Annotated[SingleAgentService, Depends(get_single_agent_service)]


def get_capability_analyser(
    providers: ProviderRegistryDep, settings: SettingsDep
) -> CapabilityAnalyser:
    return build_capability_analyser(providers, settings)


CapabilityAnalyserDep = Annotated[CapabilityAnalyser, Depends(get_capability_analyser)]


def get_engine(
    session: SessionDep, providers: ProviderRegistryDep, settings: SettingsDep
) -> WorkflowEngine:
    return build_engine(session, providers, settings)


EngineDep = Annotated[WorkflowEngine, Depends(get_engine)]


def get_orchestration_service(
    session: SessionDep, providers: ProviderRegistryDep, settings: SettingsDep
) -> OrchestrationService:
    return build_orchestration_service(session, providers, settings)


OrchestrationServiceDep = Annotated[OrchestrationService, Depends(get_orchestration_service)]


def get_workflow_runner(request: Request) -> WorkflowRunner:
    """The process-wide runner for workflows executing off the request thread.

    Created on first use rather than at startup so tests that skip lifespan still get a
    runner wired to their own session factory.
    """
    runner: WorkflowRunner | None = getattr(request.app.state, "workflow_runner", None)
    if runner is None:
        runner = WorkflowRunner(
            request.app.state.session_factory,
            request.app.state.provider_registry,
            request.app.state.settings,
        )
        request.app.state.workflow_runner = runner
    return runner


WorkflowRunnerDep = Annotated[WorkflowRunner, Depends(get_workflow_runner)]
