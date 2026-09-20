"""Assembling the orchestration stack for a given session.

FastAPI's dependency graph builds this per request, and the background runner builds it
per run with its own session. Both go through here so there is one definition of how the
pieces fit together — two versions would drift, and the one used off the request thread
is the one nobody is watching.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import DatabaseAgentRegistry, OverlayAgentRegistry
from app.core.config import Settings
from app.orchestration.capability_analysis import (
    CapabilityAnalyser,
    HeuristicCapabilityAnalyser,
    LLMCapabilityAnalyser,
)
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import AgentSelector
from app.providers.registry import ProviderRegistry
from app.schemas.agent import AgentDefinition
from app.services.agent_executor import AgentExecutor
from app.services.collaboration import Collaboration
from app.services.orchestration_service import OrchestrationService
from app.services.workflow_repository import WorkflowRepository
from app.workflows.engine import WorkflowEngine


def build_capability_analyser(
    providers: ProviderRegistry, settings: Settings
) -> CapabilityAnalyser:
    """Model-backed analysis when configured, heuristics otherwise.

    The LLM analyser already falls back to heuristics on failure; the switch exists so
    an operator can opt out of paying for an analysis call at all.
    """
    if not settings.use_llm_capability_analysis:
        return HeuristicCapabilityAnalyser()
    return LLMCapabilityAnalyser(providers, HeuristicCapabilityAnalyser())


def build_engine(
    session: AsyncSession, providers: ProviderRegistry, settings: Settings
) -> WorkflowEngine:
    registry = DatabaseAgentRegistry(session)
    return WorkflowEngine(
        registry,
        AgentExecutor(providers),
        WorkflowRepository(session),
        collaboration=Collaboration(session, registry, providers=providers),
        max_parallel_agents=settings.max_parallel_agents,
        max_repair_cycles=settings.max_repair_cycles,
    )


def build_generative_engine(
    session: AsyncSession,
    providers: ProviderRegistry,
    settings: Settings,
    ephemeral: dict[str, AgentDefinition],
) -> WorkflowEngine:
    """An engine whose registry resolves this run's generated agents by id.

    Same wiring as ``build_engine``, but over an overlay registry so the ephemeral team
    is executable without being persisted into the shared ``agents`` table.
    """
    registry = OverlayAgentRegistry(DatabaseAgentRegistry(session), ephemeral)
    return WorkflowEngine(
        registry,
        AgentExecutor(providers),
        WorkflowRepository(session),
        collaboration=Collaboration(session, registry, providers=providers),
        max_parallel_agents=settings.max_parallel_agents,
        max_repair_cycles=settings.max_repair_cycles,
    )


def build_orchestration_service(
    session: AsyncSession, providers: ProviderRegistry, settings: Settings
) -> OrchestrationService:
    registry = DatabaseAgentRegistry(session)
    return OrchestrationService(
        build_capability_analyser(providers, settings),
        AgentSelector(registry),
        WorkflowPlanner(),
        build_engine(session, providers, settings),
        WorkflowRepository(session),
        providers=providers,
    )
