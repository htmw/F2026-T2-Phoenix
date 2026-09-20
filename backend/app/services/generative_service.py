"""Level 3 orchestration: design a bespoke agent team, then run it.

This is the generative counterpart to ``OrchestrationService``. Instead of selecting
from a fixed registry, it asks the meta-planner to design a team for the request,
compiles that team into ephemeral agents and a graph, and runs it on the same engine.

It runs synchronously: the generated agents live only in memory for this request, so the
run is executed here rather than handed to the background runner (which would rebuild the
stack from the database and never see them).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import DecisionKind
from app.messaging.store import DecisionService
from app.orchestration.team_designer import TeamDesigner, build_team
from app.providers.registry import ProviderRegistry
from app.schemas.memory import DecisionCreate
from app.schemas.team import TeamSpec
from app.schemas.workflow import TaskRequest, WorkflowPlan
from app.services.factory import build_generative_engine
from app.services.orchestration_service import OrchestrationResult
from app.services.workflow_repository import WorkflowRepository

logger = get_logger(__name__)


class GenerativeOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        providers: ProviderRegistry,
        settings: Settings,
        repository: WorkflowRepository,
    ) -> None:
        self._session = session
        self._providers = providers
        self._settings = settings
        self._repository = repository
        self._designer = TeamDesigner(providers)

    async def submit(
        self, request: TaskRequest, *, owner_id: str = "operator"
    ) -> OrchestrationResult:
        """Design a team for the request, persist the plan, and execute it to completion."""
        budget = request.max_cost_usd or self._settings.generative_default_budget_usd
        spec = await self._designer.design(
            request.request, max_agents=self._settings.generative_max_agents
        )
        agents, plan = build_team(
            request.request, spec, providers=self._providers, budget_usd=budget
        )

        task = await self._repository.create_task(request, owner_id=owner_id)
        workflow = await self._repository.create_workflow(task.id, plan, owner_id=owner_id)
        await self._record_design_decision(workflow.id, spec, plan)
        await self._repository.commit()

        logger.info(
            "generative_task_submitted",
            task_id=str(task.id),
            workflow_id=str(workflow.id),
            domain=spec.domain,
            agents=[agent.id for agent in agents],
            budget_usd=budget,
            per_agent_cap_usd=agents[0].limits.max_cost_usd if agents else None,
        )

        engine = build_generative_engine(
            self._session, self._providers, self._settings, {agent.id: agent for agent in agents}
        )
        run = await engine.run(workflow.id, task.id, plan, budget_usd=budget)
        refreshed = await self._repository.get_workflow(workflow.id)
        return OrchestrationResult(workflow=refreshed, run=run)

    async def _record_design_decision(
        self, workflow_id: uuid.UUID, spec: TeamSpec, plan: WorkflowPlan
    ) -> None:
        await DecisionService(self._session).record(
            DecisionCreate(
                kind=DecisionKind.SELECTION,
                actor_id="team-designer",
                workflow_id=workflow_id,
                title=f"Designed {spec.domain} team ({len(spec.agents)} agents)",
                summary=spec.reasoning or f"Generated a {len(spec.agents)}-agent team",
                payload={
                    "domain": spec.domain,
                    "agents": [
                        {"role": a.role, "is_synthesizer": a.is_synthesizer} for a in spec.agents
                    ],
                    "nodes": [node.key for node in plan.nodes],
                    "edges": [(edge.source, edge.target) for edge in plan.edges],
                },
                tags=("generative", "team-design"),
                importance=0.85,
            )
        )
