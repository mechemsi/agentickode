# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""StatusSyncer — listens to run events and updates external task trackers."""

import asyncio
import logging

from backend.database import async_session
from backend.models.runs import TaskRun
from backend.services.http_client import get_http_client
from backend.services.task_management.factory import get_task_manager
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("agentickode.task_management.status_sync")

# Map broadcaster events to external status names
_EVENT_STATUS_MAP = {
    "run_started": "in_progress",
    "run_completed": "done",
    "run_failed": "failed",
}


class StatusSyncer:
    """Subscribe to broadcaster events and sync status to external task trackers."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._bg_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
            logger.info("Status syncer started")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Status syncer stopped")

    async def _run(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()  # type: ignore[type-arg]
        broadcaster.subscribe_global(queue)
        try:
            while True:
                payload = await queue.get()
                event_type = payload.get("type", "")
                status = _EVENT_STATUS_MAP.get(event_type)
                if status is None:
                    continue
                run_id = payload.get("run_id")
                if not run_id:
                    continue
                task = asyncio.create_task(self._sync(run_id, status, payload))
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe_global(queue)

    async def _sync(self, run_id: int, status: str, payload: dict) -> None:
        """Look up the run's task source and update external tracker."""
        try:
            async with async_session() as session:
                from sqlalchemy import select

                result = await session.execute(select(TaskRun).where(TaskRun.id == run_id))
                run = result.scalar_one_or_none()
                if not run or not run.task_source or not run.task_source_meta:
                    return

                # Skip sources that don't support bidirectional sync
                if run.task_source in ("manual", "scheduled", "automation"):
                    return

                client = get_http_client()
                manager = get_task_manager(run.task_source, client)
                await manager.update_status(run.task_source_meta, status)

                # Also post a comment for key status changes
                if status in ("done", "failed"):
                    pr_url = run.pr_url or ""
                    comment = f"**AgenticKode Run #{run.id}** — {status.upper()}"
                    if pr_url:
                        comment += f"\nPR: {pr_url}"
                    await manager.add_comment(run.task_source_meta, comment)

        except Exception:
            logger.exception("Status sync failed for run %d", run_id)
