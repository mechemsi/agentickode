# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Background scheduler that dispatches due ScheduledTask entries as TaskRun rows.

Runs alongside WorkerEngine and polls the scheduled_tasks table on a fixed interval.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.agents import ScheduledTask
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.scheduled_task_repo import ScheduledTaskRepository
from backend.services.cron_parser import next_occurrence
from backend.services.run_factory import create_task_run

logger = logging.getLogger("agentickode.scheduler")


class TaskScheduler:
    """Polls scheduled_tasks and creates TaskRun rows for due entries."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_seconds: int = 30,
    ):
        self._session_factory = session_factory
        self._poll_seconds = poll_seconds
        self._running = False

    async def run(self) -> None:
        """Main loop — poll for due tasks and dispatch."""
        self._running = True
        logger.info("TaskScheduler started (poll=%ds)", self._poll_seconds)
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self._poll_seconds)

    def stop(self) -> None:
        self._running = False
        logger.info("TaskScheduler stopping")

    async def _tick(self) -> None:
        async with self._session_factory() as session:
            repo = ScheduledTaskRepository(session)
            due_tasks = await repo.list_due()
            for task in due_tasks:
                await self._dispatch(task, session, repo)
            await session.commit()

    async def _dispatch(
        self,
        task: ScheduledTask,
        session: AsyncSession,
        repo: ScheduledTaskRepository,
    ) -> None:
        """Create a TaskRun from a due ScheduledTask."""
        project_repo = ProjectConfigRepository(session)
        project = await project_repo.get_by_id(task.project_id)
        if not project:
            logger.warning("Scheduled task %d: project %s not found", task.id, task.project_id)
            return

        task_id = f"sched-{task.id}-{uuid.uuid4().hex[:8]}"
        run = create_task_run(
            task_id=task_id,
            project=project,
            title=f"[Scheduled] {task.name}",
            description=task.task_description,
            task_source="scheduled",
            task_source_meta={
                "scheduled_task_id": task.id,
                "schedule": task.schedule,
                "scheduled_task_name": task.name,
            },
        )
        session.add(run)
        await session.flush()

        next_run = next_occurrence(task.schedule, datetime.now(UTC))
        await repo.mark_executed(task, next_run)

        logger.info(
            "Dispatched scheduled run #%d for task '%s' (next: %s)",
            run.id,
            task.name,
            next_run.isoformat(),
        )
