"""Sprint 2 data pipeline: cleaner → analyst ordering and retry default."""

from __future__ import annotations

from app.agents.builtin import BUILTIN_AGENTS, DATA_ANALYST_AGENT
from app.agents.registry import InMemoryAgentRegistry
from app.domain.enums import Capability
from app.orchestration.capability_analysis import CapabilityAnalysis
from app.orchestration.planner import WorkflowPlanner
from app.orchestration.selection import AgentSelector
from app.schemas.agent import RetryPolicy


async def test_data_pipeline_orders_cleaner_before_analyst() -> None:
    registry = InMemoryAgentRegistry(list(BUILTIN_AGENTS))
    capabilities = frozenset(
        {
            Capability.DATA_CLEANING,
            Capability.DATA_ANALYSIS,
            Capability.REPORT_GENERATION,
        }
    )
    selection = await AgentSelector(registry).select(capabilities)
    analysis = CapabilityAnalysis(
        required=capabilities,
        reasoning="clean then analyse then report",
        source="test",
    )
    plan = WorkflowPlanner().plan(
        "Clean this CSV, analyse trends, and write a report", analysis, selection
    )

    cleaner = next(node for node in plan.nodes if Capability.DATA_CLEANING in node.satisfies)
    analyst = next(node for node in plan.nodes if Capability.DATA_ANALYSIS in node.satisfies)
    assert any(edge.source == cleaner.key and edge.target == analyst.key for edge in plan.edges), [
        (edge.source, edge.target) for edge in plan.edges
    ]


def test_retry_policy_defaults_to_three_attempts() -> None:
    assert RetryPolicy().max_attempts == 3
    assert DATA_ANALYST_AGENT.retry_policy.max_attempts == 3
