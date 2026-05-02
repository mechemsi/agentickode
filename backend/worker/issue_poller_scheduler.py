# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Background scheduler that polls open issues and dispatches TaskRuns.

Runs every ``_poll_seconds``. On each tick:

1. Query ``ProjectConfig`` rows where ``poll_enabled=True`` and the next poll
   time has elapsed.
2. Dispatch the source-specific ``IssuePoller`` for each project.
3. Update ``last_polled_at`` and ``next_poll_at``.

Errors on a single project are logged and swallowed so one bad config does not
stall the scheduler.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.models import ProjectConfig
from backend.services.task_source_polling.factory import get_poller

logger = logging.getLogger("agentickode.issue_poller_scheduler")


class IssuePollerScheduler:
    """Polls external issue trackers on a per-project schedule."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_seconds: int = 60,
    ):
        self._session_factory = session_factory
        self._poll_seconds = poll_seconds
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info("IssuePollerScheduler started (tick=%ds)", self._poll_seconds)
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Issue poller tick failed")
            await asyncio.sleep(self._poll_seconds)

    def stop(self) -> None:
        self._running = False
        logger.info("IssuePollerScheduler stopping")

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            due = await self._due_projects(session, now)
            if not due:
                return
            logger.debug("IssuePollerScheduler: %d project(s) due", len(due))
            for project in due:
                await self._poll_project(session, project, now)
            await session.commit()

    async def _due_projects(self, session: AsyncSession, now: datetime) -> list[ProjectConfig]:
        stmt = (
            select(ProjectConfig)
            .options(selectinload(ProjectConfig.workspace_servers))
            .where(
                ProjectConfig.poll_enabled.is_(True),
                or_(
                    ProjectConfig.next_poll_at.is_(None),
                    ProjectConfig.next_poll_at <= now,
                ),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _poll_project(
        self, session: AsyncSession, project: ProjectConfig, now: datetime
    ) -> None:
        poller = get_poller(project.task_source)
        if poller is None:
            logger.debug(
                "No poller for task_source=%s on project %s",
                project.task_source,
                project.project_id,
            )
            # Still advance next_poll_at so we don't spin on unsupported sources.
            self._advance(project, now)
            return

        try:
            created = await poller.poll(project, session)
            if created:
                logger.info(
                    "Polled %s: %d new run(s) for project %s",
                    project.task_source,
                    len(created),
                    project.project_id,
                )
        except Exception:
            logger.exception(
                "Poller for %s failed on project %s",
                project.task_source,
                project.project_id,
            )
        self._advance(project, now)

    def _advance(self, project: ProjectConfig, now: datetime) -> None:
        project.last_polled_at = now
        interval = max(1, int(project.poll_interval_minutes or 5))
        project.next_poll_at = now + timedelta(minutes=interval)
