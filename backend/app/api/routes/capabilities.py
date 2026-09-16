"""Capability catalogue.

Exposes the vocabulary the orchestrator reasons about, along with which agents cover
each capability, so a gap in coverage is visible rather than showing up as a workflow
that silently cannot be planned.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.dependencies import RegistryDep
from app.domain.enums import Capability

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


class CapabilityCoverage(BaseModel):
    capability: Capability
    agent_ids: list[str]
    covered: bool


@router.get("", response_model=list[CapabilityCoverage], summary="List capabilities")
async def list_capabilities(registry: RegistryDep) -> list[CapabilityCoverage]:
    coverage = await registry.find_by_capabilities(set(Capability))
    return [
        CapabilityCoverage(
            capability=capability,
            agent_ids=sorted(definition.id for definition in definitions),
            covered=bool(definitions),
        )
        for capability, definitions in sorted(coverage.items())
    ]
