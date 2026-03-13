# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Worker engine — polling loop that dispatches task runs.

Replaces Temporal worker. Runs as an asyncio background task inside
the FastAPI process (started from lifespan).
"""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.config import settings
from backend.database import async_session
from backend.dependencies import get_service_container
from backend.models import PhaseExecution, TaskRun
from backend.repositories.app_setting_repo import AppSettingRepository
from backend.services.container import ServiceContainer
from backend.services.schedule import is_within_schedule
from backend.worker.broadcaster import broadcaster
from backend.worker.pipeline import execute_pipeline

logger = logging.getLogger("agentickode.worker")


class WorkerEngine:
    SCHEDULE_CACHE_TTL = 60  # seconds

    def __init__(self):
        self._running = False
        self._active_runs: dict[int, asyncio.Task] = {}
        self._services: ServiceContainer | None = None
        self._schedule_cache: dict | None = None
        self._schedule_loaded_at: float = 0.0

    def _get_services(self) -> ServiceContainer:
        if self._services is None:
            self._services = get_service_container()
        return self._services

    async def _get_schedule(self, session) -> dict | None:
        """Load queue_schedule setting with TTL cache."""
        now = time.monotonic()
        if now - self._schedule_loaded_at < self.SCHEDULE_CACHE_TTL:
            return self._schedule_cache
        repo = AppSettingRepository(session)
        self._schedule_cache = await repo.get("queue_schedule")
        self._schedule_loaded_at = now
        return self._schedule_cache

    def stop(self):
        self._running = False

    async def run(self):
        """Main polling loop — runs every POLL_INTERVAL_SECONDS."""
        self._running = True
        logger.info(
            f"Worker started (max_concurrent={settings.max_concurrent_runs}, "
            f"poll_interval={settings.poll_interval_seconds}s)"
        )
        await self._recover_interrupted_runs()
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Worker tick failed")
            await asyncio.sleep(settings.poll_interval_seconds)

    async def _recover_interrupted_runs(self):
        """Reset runs interrupted by a restart so they resume from the last completed phase."""
        async with async_session() as session:
            result = await session.execute(select(TaskRun).where(TaskRun.status == "running"))
            interrupted = result.scalars().all()
            if not interrupted:
                return
            for run in interrupted:
                # Reset any phase that was mid-execution back to pending
                phase_result = await session.execute(
                    select(PhaseExecution).where(
                        PhaseExecution.run_id == run.id,
                        PhaseExecution.status == "running",
                    )
                )
                for pe in phase_result.scalars().all():
                    pe.status = "pending"
                    pe.started_at = None
                run.status = "pending"
                logger.info(f"Recovered interrupted run #{run.id}, resetting to pending")
            await session.commit()

    async def _tick(self):
        # Cleanup completed/failed tasks from active set
        done = [rid for rid, task in self._active_runs.items() if task.done()]
        for rid in done:
            task = self._active_runs.pop(rid)
            if task.exception():
                logger.error(f"Run #{rid} task raised: {task.exception()}")

        async with async_session() as session:
            await self._dispatch_pending(session)
            await self._handle_waiting(session)
            await self._handle_timeouts(session)

    async def _dispatch_pending(self, session):
        available_slots = settings.max_concurrent_runs - len(self._active_runs)
        if available_slots <= 0:
            return

        # Projects that already have an active run — skip their pending runs
        active_statuses = ("running", "waiting_for_trigger")
        active_projects_q = (
            select(TaskRun.project_id).where(TaskRun.status.in_(active_statuses)).distinct()
        )

        result = await session.execute(
            select(TaskRun)
            .where(
                TaskRun.status == "pending",
                TaskRun.project_id.notin_(active_projects_q),
            )
            .order_by(TaskRun.created_at)
            .limit(available_slots)
        )
        runs = result.scalars().all()

        schedule = await self._get_schedule(session)
        within_schedule = is_within_schedule(schedule)

        # Only dispatch one run per project per tick to avoid racing
        dispatched_projects: set[str] = set()
        for run in runs:
            if run.project_id in dispatched_projects:
                continue
            if not within_schedule:
                meta = run.task_source_meta or {}
                if not meta.get("skip_schedule", False):
                    continue  # blocked by schedule
            dispatched_projects.add(run.project_id)
            logger.info(f"Dispatching run #{run.id}: {run.title}")
            task = asyncio.create_task(self._run_pipeline(run.id))
            self._active_runs[run.id] = task

    async def _run_pipeline(self, run_id: int):
        """Execute pipeline with its own session."""
        async with async_session() as session:
            run = await session.get(TaskRun, run_id)
            if not run or run.status != "pending":
                return
            try:
                await execute_pipeline(run, session, self._get_services())
            except Exception:
                logger.exception(f"Pipeline failed for run #{run_id}")
                await session.refresh(run)
                run.status = "failed"
                run.error_message = "Unhandled pipeline error"
                run.completed_at = datetime.now(UTC)
                await session.commit()

    async def _handle_waiting(self, session):
        """Pick up runs where a waiting phase can now be resumed."""
        # 1. Runs awaiting approval where human has decided
        result = await session.execute(
            select(TaskRun).where(
                TaskRun.status == "awaiting_approval",
                TaskRun.approved.isnot(None),
            )
        )
        for run in result.scalars().all():
            if run.id in self._active_runs:
                continue
            if run.approved:
                logger.info(f"Resuming run #{run.id} after approval")
                # Find the waiting phase and set it to completed, advance run
                waiting_phase = await session.execute(
                    select(PhaseExecution).where(
                        PhaseExecution.run_id == run.id,
                        PhaseExecution.status == "waiting",
                        PhaseExecution.trigger_mode == "wait_for_approval",
                    )
                )
                pe = waiting_phase.scalar_one_or_none()
                if pe:
                    pe.status = "completed"
                    pe.completed_at = datetime.now(UTC)
                run.status = "pending"
                await session.commit()
                task = asyncio.create_task(self._run_pipeline(run.id))
                self._active_runs[run.id] = task
            else:
                logger.info(f"Run #{run.id} was rejected")
                # Mark the waiting phase as failed
                waiting_phase = await session.execute(
                    select(PhaseExecution).where(
                        PhaseExecution.run_id == run.id,
                        PhaseExecution.status == "waiting",
                    )
                )
                pe = waiting_phase.scalar_one_or_none()
                if pe:
                    pe.status = "failed"
                    pe.error_message = f"Rejected: {run.rejection_reason or 'No reason given'}"
                    pe.completed_at = datetime.now(UTC)
                run.status = "failed"
                run.error_message = f"Rejected: {run.rejection_reason or 'No reason given'}"
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await broadcaster.event(run.id, "run_rejected", {"reason": run.rejection_reason})

        # 2. Runs waiting for external trigger where phase was advanced
        result = await session.execute(
            select(TaskRun).where(TaskRun.status == "waiting_for_trigger")
        )
        for run in result.scalars().all():
            if run.id in self._active_runs:
                continue
            # Check if the waiting phase has been advanced to pending
            pending = await session.execute(
                select(PhaseExecution).where(
                    PhaseExecution.run_id == run.id,
                    PhaseExecution.status == "pending",
                )
            )
            if pending.scalar_one_or_none():
                logger.info(f"Resuming run #{run.id} after trigger advance")
                run.status = "pending"
                await session.commit()
                task = asyncio.create_task(self._run_pipeline(run.id))
                self._active_runs[run.id] = task

    async def _handle_timeouts(self, session):
        """Mark runs that have been awaiting approval beyond the timeout."""
        cutoff = datetime.now(UTC) - timedelta(hours=settings.approval_timeout_hours)
        result = await session.execute(
            select(TaskRun).where(
                TaskRun.status == "awaiting_approval",
                TaskRun.approved.is_(None),
                TaskRun.approval_requested_at < cutoff,
            )
        )
        for run in result.scalars().all():
            logger.warning(f"Run #{run.id} timed out waiting for approval")
            run.status = "timeout"
            run.error_message = f"Approval timeout after {settings.approval_timeout_hours}h"
            run.completed_at = datetime.now(UTC)
            await session.commit()
            await broadcaster.event(run.id, "run_timeout", {"run_id": run.id})
