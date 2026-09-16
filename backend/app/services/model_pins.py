"""Apply model pins onto agent definitions and workflow nodes."""

from __future__ import annotations

from app.domain.enums import RoutingStrategy
from app.schemas.agent import AgentDefinition, ModelPreference
from app.schemas.workflow import TaskRequest, WorkflowNode, WorkflowPlan


def pin_model(agent: AgentDefinition, model_id: str) -> AgentDefinition:
    """Return a copy of ``agent`` that prefers ``model_id`` (and its provider)."""
    provider = model_id.split(":", 1)[0] if ":" in model_id else None
    preference = agent.model_preference.model_copy(
        update={"preferred_model": model_id, "preferred_provider": provider}
    )
    return agent.model_copy(update={"model_preference": preference})


def clear_model_pin(agent: AgentDefinition) -> AgentDefinition:
    """Return a copy of ``agent`` with Fixed binding cleared (Auto)."""
    preference = agent.model_preference.model_copy(
        update={"preferred_model": None, "preferred_provider": None}
    )
    return agent.model_copy(update={"model_preference": preference})


def bake_model_into_parameters(
    parameters: dict[str, object], model_id: str | None
) -> dict[str, object]:
    """Persist the pin on the node so resume and the UI can see it."""
    if not model_id:
        return dict(parameters)
    next_params = dict(parameters)
    next_params["model"] = model_id
    return next_params


def model_id_from_parameters(parameters: dict[str, object]) -> str | None:
    value = parameters.get("model")
    return value if isinstance(value, str) and value else None


def preference_with_optional_pin(
    preference: ModelPreference, model_id: str | None
) -> ModelPreference:
    if not model_id:
        return preference
    provider = model_id.split(":", 1)[0] if ":" in model_id else None
    return preference.model_copy(
        update={"preferred_model": model_id, "preferred_provider": provider}
    )


def apply_routing_to_plan(plan: WorkflowPlan, request: TaskRequest) -> WorkflowPlan:
    """Bake One/Mixed pins onto node parameters. Auto leaves nodes untouched."""
    strategy = request.routing_strategy
    if strategy == RoutingStrategy.ONE:
        shared = request.shared_model
        if not shared:
            raise ValueError("shared_model is required for one-model routing")
        nodes = tuple(
            node.model_copy(
                update={"parameters": bake_model_into_parameters(node.parameters, shared)}
            )
            for node in plan.nodes
        )
        return plan.model_copy(update={"nodes": nodes})

    if strategy == RoutingStrategy.MIXED:
        return _apply_overrides(plan, request.model_overrides)

    return plan


def _apply_overrides(plan: WorkflowPlan, overrides: dict[str, str]) -> WorkflowPlan:
    if not overrides:
        return plan
    nodes: list[WorkflowNode] = []
    for node in plan.nodes:
        model_id = overrides.get(node.agent_id)
        if model_id:
            nodes.append(
                node.model_copy(
                    update={"parameters": bake_model_into_parameters(node.parameters, model_id)}
                )
            )
        else:
            nodes.append(node)
    return plan.model_copy(update={"nodes": tuple(nodes)})
