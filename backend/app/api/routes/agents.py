"""Agent registry endpoints.

List/get are public. Enrollment, updates and Fixed model bindings require operator
identity.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.agents.enrollment import (
    DuplicateAgentNameError,
    EnrollmentError,
    enroll_agent,
    update_agent,
)
from app.agents.registry import AgentNotFoundError, DatabaseAgentRegistry, record_to_definition
from app.agents.tables import AGENT_DATA_SCHEMA, table_name_for
from app.api.dependencies import (
    AbuseGuardDep,
    OperatorDep,
    ProviderRegistryDep,
    RegistryDep,
    SessionDep,
)
from app.core.logging import get_logger
from app.domain.enums import Capability
from app.models.agent import AgentRecord
from app.schemas.agent import AgentEnrollment, AgentModelBinding, AgentSummary, AgentUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


async def _table_names(session: SessionDep) -> dict[str, str | None]:
    rows = await session.execute(select(AgentRecord.id, AgentRecord.table_name))
    return {row.id: row.table_name for row in rows}


def _summary(record: AgentRecord) -> AgentSummary:
    return AgentSummary.from_definition(record_to_definition(record), table_name=record.table_name)


def _enrollment_error(exc: EnrollmentError) -> HTTPException:
    if isinstance(exc, DuplicateAgentNameError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("", response_model=list[AgentSummary], summary="List registered agents")
async def list_agents(
    registry: RegistryDep,
    session: SessionDep,
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
    tables = await _table_names(session)
    return [
        AgentSummary.from_definition(definition, table_name=tables.get(definition.id))
        for definition in definitions
    ]


@router.post(
    "",
    response_model=AgentSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll a new agent",
)
async def create_agent(
    body: AgentEnrollment,
    session: SessionDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> AgentSummary:
    """Enroll an agent in one request: registry row, capabilities and result table.

    The agent is Active immediately and selectable by capability. Missing fields, a
    malformed schema or a duplicate name are rejected before anything is written; if the
    result table cannot be created the whole enrollment is rolled back.
    """
    try:
        record = await enroll_agent(session, body)
    except EnrollmentError as exc:
        await session.rollback()
        raise _enrollment_error(exc) from None
    except IntegrityError:
        # Lost a race with a concurrent enrollment of the same name.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"name: an agent named '{body.name}' is already enrolled",
        ) from None
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.error("agent_enrollment_failed", name=body.name, error=str(exc)[:500])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="could not create the agent's result table; enrollment was rolled back",
        ) from None
    logger.info("agent_enrollment_accepted", agent_id=record.id, operator_id=operator.id)
    return _summary(record)


@router.get("/{agent_id}", response_model=AgentSummary, summary="Get one agent")
async def get_agent(agent_id: str, session: SessionDep) -> AgentSummary:
    record = await session.get(AgentRecord, agent_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"agent '{agent_id}' not found"
        )
    return _summary(record)


@router.patch("/{agent_id}", response_model=AgentSummary, summary="Update or disable an agent")
async def patch_agent(
    agent_id: str,
    body: AgentUpdate,
    session: SessionDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> AgentSummary:
    """Change an enrolled agent. ``{"enabled": false}`` disables it.

    A disabled agent is never offered to the orchestrator: it is excluded from
    capability lookups and rejected if named explicitly in a task.
    """
    _ = operator
    try:
        record = await update_agent(session, agent_id, body)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"agent '{agent_id}' not found"
        ) from None
    except EnrollmentError as exc:
        await session.rollback()
        raise _enrollment_error(exc) from None
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"name: an agent named '{body.name}' is already enrolled",
        ) from None
    return _summary(record)


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
    tables = await _table_names(session)
    return AgentSummary.from_definition(definition, table_name=tables.get(agent_id))


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


@router.get("/{agent_id}/records", summary="Validated results stored in the agent's table")
async def list_agent_records(
    agent_id: str,
    session: SessionDep,
    operator: OperatorDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, object]:
    """Newest rows from the agent's own table, restricted to the caller's workflows."""
    record = await session.get(AgentRecord, agent_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"agent '{agent_id}' not found"
        )
    if not record.table_name:
        return {"agent_id": agent_id, "table": None, "records": []}

    # Derived from the validated id, never from user input or the stored string.
    table = table_name_for(agent_id)
    rows = await session.execute(
        text(
            f'SELECT r.* FROM "{AGENT_DATA_SCHEMA}"."{table}" r '  # noqa: S608
            "JOIN workflows w ON w.id = r._workflow_id "
            "WHERE w.owner_id = :owner ORDER BY r._created_at DESC LIMIT :limit"
        ),
        {"owner": operator.id, "limit": limit},
    )
    records = [
        {key: _jsonable(value) for key, value in row._mapping.items() if key != "_payload"}
        for row in rows
    ]
    return {"agent_id": agent_id, "table": record.table_name, "records": records}


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool | list | dict):
        return value
    return str(value)
