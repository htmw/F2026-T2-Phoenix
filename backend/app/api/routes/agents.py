"""Agent registry endpoints.

List/get are public. Fixed model bindings require operator identity.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.agents.registry import AgentNotFoundError, DatabaseAgentRegistry
from app.api.dependencies import AbuseGuardDep, OperatorDep, ProviderRegistryDep, RegistryDep, SessionDep
from app.domain.enums import Capability
from app.schemas.agent import AgentModelBinding, AgentSummary

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentSummary], summary="List registered agents")
async def list_agents(
    registry: RegistryDep,
    capability: Annotated[
        Capability | None,
        Query(description="Return only agents providing this capability"),
    ] = None,
    include_disabled: Annotated[bool, Query()] = False,
) -> list[AgentSummary]:
    if capability is not None:
        definitions = await registry.find_by_capability(capability)
    else:
        definitions = await registry.list_all(include_disabled=include_disabled)
    return [AgentSummary.from_definition(definition) for definition in definitions]


@router.get("/{agent_id}", response_model=AgentSummary, summary="Get one agent")
async def get_agent(agent_id: str, registry: RegistryDep) -> AgentSummary:
    try:
        definition = await registry.get(agent_id)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"agent '{agent_id}' not found"
        ) from None
    return AgentSummary.from_definition(definition)


@router.patch(
    "/{agent_id}/model-binding",
    response_model=AgentSummary,
    summary="Set or clear an agent's Fixed model binding",
)
async def set_agent_model_binding(
    agent_id: str,
    body: AgentModelBinding,
    session: SessionDep,
    providers: ProviderRegistryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> AgentSummary:
    """Fixed = durable preferred_model; null preferred_model returns the agent to Auto."""
    _ = operator
    if body.preferred_model is not None:
        known = {model.id for model in providers.available_models()}
        if body.preferred_model not in known:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown or unconfigured model: {body.preferred_model}",
            )
    registry = DatabaseAgentRegistry(session)
    try:
        definition = await registry.set_model_binding(agent_id, body.preferred_model)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"agent '{agent_id}' not found"
        ) from None
    return AgentSummary.from_definition(definition)


@router.get(
    "/{agent_id}/schema",
    summary="Get an agent's input and output JSON Schema",
)
async def get_agent_schema(agent_id: str, registry: RegistryDep) -> dict[str, object]:
    """Expose the contract an agent accepts and guarantees.

    Clients need this to render results and to understand what a hand-off contains.
    Prompt instructions are deliberately not included.
    """
    try:
        definition = await registry.get(agent_id)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"agent '{agent_id}' not found"
        ) from None
    return {
        "agent_id": definition.id,
        "input_schema": definition.input_schema,
        "output_schema": definition.output_schema,
    }
