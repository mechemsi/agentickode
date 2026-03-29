# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Background scheduler for platform crons — sends prompts to agent sessions on schedule."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.repositories.platform_cron_repo import PlatformCronRepository
from backend.services.cron_parser import next_occurrence
from backend.services.platform_cron_executor import PlatformCronExecutor

logger = logging.getLogger("agentickode.platform_cron_scheduler")


class PlatformCronScheduler:
    """Polls platform_crons table and sends prompts to agent sessions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_seconds: int = 30,
    ):
        self._session_factory = session_factory
        self._poll_seconds = poll_seconds
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info("PlatformCronScheduler started (poll=%ds)", self._poll_seconds)
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Platform cron tick failed")
            await asyncio.sleep(self._poll_seconds)

    def stop(self) -> None:
        self._running = False
        logger.info("PlatformCronScheduler stopping")

    async def _tick(self) -> None:
        async with self._session_factory() as session:
            repo = PlatformCronRepository(session)
            due_crons = await repo.list_due()
            executor = PlatformCronExecutor(session)

            for cron in due_crons:
                result = await executor.execute_cron(cron)
                # Schedule next run
                cron.next_run_at = next_occurrence(cron.schedule, datetime.now(UTC))
                logger.info(
                    "Platform cron %d (%s): %s (next: %s)",
                    cron.id,
                    cron.name,
                    result,
                    cron.next_run_at.isoformat() if cron.next_run_at else "none",
                )

            await session.commit()
