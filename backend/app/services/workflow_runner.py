"""Running workflows off the request thread.

A workflow takes as long as its agents take — minutes, not milliseconds — so holding an
HTTP connection open for one is the wrong shape: the client cannot render progress, a
proxy timeout looks like a failure, and cancellation has nobody to ask.

Each run gets its own database session, because the request's session closes as soon as
the response is sent. State lives in Postgres, not in this object, so a process that
dies mid-run loses at most the batch in flight and the workflow can be resumed.

This is deliberately an in-process runner rather than a queue. It is honest about what
it is: `RUNNING` workflows survive a restart as resumable records, and a real broker can
replace this class without the API or the engine noticing.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import TaskStatus, WorkflowStatus
from app.providers.registry import ProviderRegistry
from app.services.factory import build_orchestration_service
from app.services.orchestration_service import PreparedWorkflow
from app.services.workflow_repository import WorkflowRepository

logger = get_logger(__name__)


class WorkflowRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        providers: ProviderRegistry,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._providers = providers
        self._settings = settings
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    def replace_providers(self, providers: ProviderRegistry) -> None:
        """Hot-swap the registry after Settings connect/disconnect (in-process)."""
        self._providers = providers

    @property
    def running(self) -> tuple[uuid.UUID, ...]:
        return tuple(self._tasks)

    def start(self, prepared: PreparedWorkflow) -> None:
        self._spawn(prepared.workflow_id, self._execute(prepared))

    def start_resume(self, workflow_id: uuid.UUID) -> None:
        self._spawn(workflow_id, self._resume(workflow_id))

    async def wait_for(self, workflow_id: uuid.UUID, *, seconds: float = 60.0) -> bool:
        """Block until a run finishes. For tests and scripted use, not for handlers.

        Returns False if it was still going when the deadline passed; the workflow keeps
        running and can be polled.
        """
        task = self._tasks.get(workflow_id)
        if task is None:
            return True
        try:
            async with asyncio.timeout(seconds):
                await asyncio.shield(task)
        except TimeoutError:
            return False
        return True

    async def shutdown(self) -> None:
        """Stop tracking in-flight runs on process shutdown.

        The tasks are cancelled rather than awaited: a deploy should not wait minutes
        for a workflow. Their nodes stay as they were last committed, which is what
        makes them resumable — the alternative, marking them failed, would throw away
        work that is not lost.
        """
        for workflow_id, task in list(self._tasks.items()):
            task.cancel()
            logger.info("workflow_run_abandoned", workflow_id=str(workflow_id))
        self._tasks.clear()

    # ---- internals ---------------------------------------------------------

    def _spawn(self, workflow_id: uuid.UUID, coroutine: Coroutine[Any, Any, None]) -> None:
        if workflow_id in self._tasks:
            logger.info("workflow_already_running", workflow_id=str(workflow_id))
            return
        # A reference is kept until completion; without one the event loop is free to
        # garbage-collect the task mid-run.
        task = asyncio.ensure_future(coroutine)
        self._tasks[workflow_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(workflow_id, None))

    async def _execute(self, prepared: PreparedWorkflow) -> None:
        async with self._session_factory() as session:
            service = build_orchestration_service(session, self._providers, self._settings)
            try:
                await service.execute(prepared)
            except asyncio.CancelledError:
                logger.info("workflow_run_cancelled", workflow_id=str(prepared.workflow_id))
                raise
            except Exception as exc:
                await self._record_crash(session, prepared.workflow_id, prepared.task_id, exc)

    async def _resume(self, workflow_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            service = build_orchestration_service(session, self._providers, self._settings)
            try:
                await service.resume(workflow_id)
            except asyncio.CancelledError:
                logger.info("workflow_run_cancelled", workflow_id=str(workflow_id))
                raise
            except Exception as exc:
                await self._record_crash(session, workflow_id, None, exc)

    @staticmethod
    async def _record_crash(
        session: AsyncSession,
        workflow_id: uuid.UUID,
        task_id: uuid.UUID | None,
        exc: Exception,
    ) -> None:
        """Make an unexpected crash visible instead of leaving a workflow "running".

        Nothing is watching this coroutine, so an exception that only reaches the log
        would leave the user staring at a spinner forever.
        """
        logger.exception("workflow_run_crashed", workflow_id=str(workflow_id), error=str(exc))
        await session.rollback()
        repository = WorkflowRepository(session)
        try:
            await repository.finish_workflow(
                workflow_id, WorkflowStatus.FAILED, error=f"internal error: {exc}"
            )
            if task_id is not None:
                await repository.set_task_status(task_id, TaskStatus.FAILED)
            await repository.commit()
        except Exception:  # pragma: no cover - the database itself is the problem
            logger.exception("workflow_crash_not_recorded", workflow_id=str(workflow_id))
