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
from backend.models.servers import WorkspaceServer
from backend.repositories.app_setting_repo import AppSettingRepository
from backend.services.container import ServiceContainer
from backend.services.git.protocol import get_git_provider
from backend.services.http_client import get_http_client
from backend.services.queue_service import queue_service
from backend.services.schedule import is_within_schedule
from backend.services.workspace.ssh_service import SSHService
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._helpers import get_project_token
from backend.worker.pipeline import execute_pipeline

logger = logging.getLogger("agentickode.worker")


class WorkerEngine:
    SCHEDULE_CACHE_TTL = 60  # seconds
    PR_CHECK_INTERVAL = 3600  # seconds
    SESSION_CHECK_INTERVAL = 30  # seconds

    def __init__(self):
        self._running = False
        self._active_runs: dict[int, asyncio.Task] = {}
        self._services: ServiceContainer | None = None
        self._schedule_cache: dict | None = None
        self._schedule_loaded_at: float = 0.0
        self._pr_check_last_run: float = 0.0
        self._session_check_last_run: float = 0.0

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
                # Still clean up stale Redis entries even when no DB runs are interrupted
                await queue_service.cleanup_stale_entries(set())
                return
            interrupted_ids: set[int] = set()
            for run in interrupted:
                interrupted_ids.add(run.id)
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

            # Sync Redis state: only keep runs that are genuinely active
            active_result = await session.execute(
                select(TaskRun.id).where(TaskRun.status.in_(("running", "pending")))
            )
            valid_ids = {r[0] for r in active_result.all()}
            await queue_service.cleanup_stale_entries(valid_ids)

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

        now = time.monotonic()
        if now - self._pr_check_last_run >= self.PR_CHECK_INTERVAL:
            self._pr_check_last_run = now
            async with async_session() as session:
                await self._check_pr_statuses(session)

        if now - self._session_check_last_run >= self.SESSION_CHECK_INTERVAL:
            self._session_check_last_run = now
            try:
                async with async_session() as session:
                    await self._check_sessions(session)
            except Exception:
                logger.exception("Session health check failed")

    async def _dispatch_pending(self, session):
        available_slots = settings.max_concurrent_runs - len(self._active_runs)
        if available_slots <= 0:
            return

        # (project_id, workspace_server_id) pairs that already have an active run
        # — skip further pending runs with the same combination
        active_statuses = ("running", "waiting_for_trigger")
        active_workspaces_q = (
            select(TaskRun.project_id, TaskRun.workspace_server_id)
            .where(TaskRun.status.in_(active_statuses))
            .distinct()
        )
        active_ws_result = await session.execute(active_workspaces_q)
        active_workspaces: set[tuple[str, int | None]] = set(active_ws_result.tuples())

        result = await session.execute(
            select(TaskRun)
            .where(TaskRun.status == "pending")
            .order_by(TaskRun.created_at)
            .limit(available_slots * 10)  # fetch more to account for filtering
        )
        runs = result.scalars().all()

        schedule = await self._get_schedule(session)
        within_schedule = is_within_schedule(schedule)

        # Cache server concurrency limits per tick to avoid repeated DB lookups
        server_limits: dict[int, int] = {}

        # Only dispatch one run per (project, workspace) pair per tick to avoid racing
        dispatched_workspaces: set[tuple[str, int | None]] = set()
        dispatched_count = 0
        for run in runs:
            if dispatched_count >= available_slots:
                break
            dispatch_key = (run.project_id, run.workspace_server_id)
            if dispatch_key in active_workspaces:
                continue
            if dispatch_key in dispatched_workspaces:
                continue
            if not within_schedule:
                meta = run.task_source_meta or {}
                if not meta.get("skip_schedule", False):
                    continue  # blocked by schedule

            # Check per-server concurrency limit
            sid = run.workspace_server_id
            if sid:
                if sid not in server_limits:
                    server = await session.get(WorkspaceServer, sid)
                    server_limits[sid] = server.max_concurrent_tasks if server else 1
                active_on_server = await queue_service.get_server_active_count(sid)
                if active_on_server >= server_limits[sid]:
                    continue  # server at capacity

            dispatched_workspaces.add(dispatch_key)
            dispatched_count += 1
            logger.info(f"Dispatching run #{run.id}: {run.title}")
            task = asyncio.create_task(self._run_pipeline(run.id))
            self._active_runs[run.id] = task

    async def _run_pipeline(self, run_id: int):
        """Execute pipeline with its own session."""
        server_id: int | None = None
        async with async_session() as session:
            run = await session.get(TaskRun, run_id)
            if not run or run.status != "pending":
                return
            server_id = int(run.workspace_server_id) if run.workspace_server_id else None
            if server_id:
                await queue_service.mark_run_started(run_id, server_id)
            try:
                await execute_pipeline(run, session, self._get_services())
            except Exception:
                logger.exception(f"Pipeline failed for run #{run_id}")
                await session.refresh(run)
                run.status = "failed"
                run.error_message = "Unhandled pipeline error"
                run.completed_at = datetime.now(UTC)
                await session.commit()
            finally:
                if server_id:
                    await queue_service.mark_run_completed(run_id, server_id)

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
                await self._resume_approved_run(run, session)
            else:
                await self._reject_run(run, session)

        # 2. Runs waiting for external trigger where phase was advanced
        result = await session.execute(
            select(TaskRun).where(TaskRun.status == "waiting_for_trigger")
        )
        for run in result.scalars().all():
            if run.id in self._active_runs:
                continue
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

    async def _resume_approved_run(self, run: TaskRun, session) -> None:
        """Mark the waiting approval phase complete and re-queue the run."""
        logger.info(f"Resuming run #{run.id} after approval")
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

    async def _reject_run(self, run: TaskRun, session) -> None:
        """Mark the waiting phase and the run itself as failed due to rejection."""
        logger.info(f"Run #{run.id} was rejected")
        reason = f"Rejected: {run.rejection_reason or 'No reason given'}"
        waiting_phase = await session.execute(
            select(PhaseExecution).where(
                PhaseExecution.run_id == run.id,
                PhaseExecution.status == "waiting",
            )
        )
        pe = waiting_phase.scalar_one_or_none()
        if pe:
            pe.status = "failed"
            pe.error_message = reason
            pe.completed_at = datetime.now(UTC)
        run.status = "failed"
        run.error_message = reason
        run.completed_at = datetime.now(UTC)
        await session.commit()
        await broadcaster.event(run.id, "run_rejected", {"reason": run.rejection_reason})

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

    async def _check_pr_statuses(self, session):
        """Check PR status for awaiting-approval runs and auto-approve/reject."""
        result = await session.execute(
            select(TaskRun).where(
                TaskRun.status == "awaiting_approval",
                TaskRun.approved.is_(None),
                TaskRun.pr_url.isnot(None),
            )
        )
        runs = result.scalars().all()
        if not runs:
            return

        client = get_http_client()
        for run in runs:
            try:
                project_token = await get_project_token(run, session)
                provider = get_git_provider(run.git_provider, client, access_token=project_token)
                status = await provider.get_pr_status(run.pr_url)
            except Exception:
                logger.warning(f"Run #{run.id}: failed to check PR status", exc_info=True)
                continue

            if status == "merged":
                logger.info(f"Run #{run.id}: PR merged externally, auto-approving")
                run.approved = True
                await session.commit()
            elif status == "closed":
                logger.info(f"Run #{run.id}: PR closed externally, auto-rejecting")
                run.approved = False
                run.rejection_reason = "PR was closed in git provider"
                await session.commit()

    async def _check_sessions(self, session):
        """Check health of active CLI sessions by verifying tmux on remote servers."""
        from backend.models.sessions import CliSession

        result = await session.execute(
            select(CliSession).where(
                CliSession.status.in_(["starting", "active", "idle", "detached"])
            )
        )
        sessions_list = result.scalars().all()
        if not sessions_list:
            return

        # Group by server
        by_server: dict[int, list] = {}
        for s in sessions_list:
            by_server.setdefault(s.workspace_server_id, []).append(s)

        for server_id, cli_sessions in by_server.items():
            try:
                server = await session.get(WorkspaceServer, server_id)
                if not server:
                    for cs in cli_sessions:
                        cs.status = "error"
                        cs.closed_at = datetime.now(UTC)
                    continue

                ssh = SSHService.for_server(server)
                # Get list of active tmux sessions in one SSH call
                try:
                    stdout, _stderr, _exit_code = await ssh.run_command(
                        "tmux list-sessions -F '#{session_name}' 2>/dev/null || true"
                    )
                    active_tmux = set(stdout.strip().split("\n")) if stdout.strip() else set()
                except Exception:
                    active_tmux = set()

                for cs in cli_sessions:
                    if cs.tmux_session not in active_tmux:
                        logger.info(
                            f"Session {cs.session_id} ({cs.tmux_session}) tmux died, marking closed"
                        )
                        cs.status = "closed"
                        cs.closed_at = datetime.now(UTC)
            except Exception:
                logger.warning(f"Failed to check sessions on server {server_id}", exc_info=True)

        await session.commit()
