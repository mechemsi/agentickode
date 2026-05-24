# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Background scheduler that removes orphaned per-run worktrees.

Catches the long-tail of cases where ``finalization._cleanup_worktree_if_any``
didn't run (crashed worker, agent kill, network split). Walks every
``WorkspaceServer`` and asks ``git worktree list`` for the worktrees it
knows about; for each ``run-<id>-<ts>`` entry we look up the TaskRun and
remove only those whose owning run is in a terminal state and whose
timestamp suffix is older than the retention window.

Defaults are conservative — hourly poll, 7-day retention — chosen so a
human still has time to ssh in and look at a recent failure's workspace
before it disappears. Tune ``poll_seconds`` / ``retention_days`` per
deployment if disks fill faster than that.

Iterates ``WorkspaceServer`` rows directly because that's the unit of
truth for "where worktrees physically live"; resolving each server's
project roots via ``workspace_result.base_clone_path`` from prior runs
avoids hard-coding the server's directory layout.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models import TaskRun, WorkspaceServer
from backend.services.workspace.command_executor import executor_for_server
from backend.services.workspace.worktree import WorktreeManager, WorktreePaths

logger = logging.getLogger("agentickode.worktree_cleanup_scheduler")

# Run dirs created by make_worktree_paths look like ``run-<id>-<ts>``.
_WORKTREE_NAME_RE = re.compile(r"^run-(?P<run_id>\d+)-(?P<ts>\d+)$")

# Terminal statuses — anything past which the run will not write to its
# workspace again. Keep in sync with TaskRun status vocabulary.
_TERMINAL_STATUSES = ("completed", "failed", "timeout", "cancelled")


class WorktreeCleanupScheduler:
    """Polls every ``poll_seconds`` and removes orphaned worktrees."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_seconds: int = 3600,
        retention_days: int = 7,
    ):
        self._session_factory = session_factory
        self._poll_seconds = poll_seconds
        self._retention_days = retention_days
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info(
            "WorktreeCleanupScheduler started (poll=%ds, retention=%dd)",
            self._poll_seconds,
            self._retention_days,
        )
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("WorktreeCleanupScheduler tick failed")
            await asyncio.sleep(self._poll_seconds)

    def stop(self) -> None:
        self._running = False
        logger.info("WorktreeCleanupScheduler stopping")

    async def _tick(self) -> None:
        """One sweep: per server, find orphaned worktrees and remove them."""
        cutoff = int(datetime.now(UTC).timestamp()) - self._retention_days * 86400
        async with self._session_factory() as session:
            servers = await self._list_servers(session)
            for server in servers:
                try:
                    await self._sweep_server(session, server, cutoff)
                except Exception:
                    logger.exception("Failed sweeping worktrees on server id=%s", server.id)

    @staticmethod
    async def _list_servers(session: AsyncSession) -> list[WorkspaceServer]:
        result = await session.execute(select(WorkspaceServer))
        return list(result.scalars().all())

    async def _sweep_server(
        self,
        session: AsyncSession,
        server: WorkspaceServer,
        cutoff_ts: int,
    ) -> None:
        """Inspect every project root we've ever used on this server."""
        roots = await self._project_roots_for_server(session, server.id)
        if not roots:
            return

        executor = executor_for_server(server)
        manager = WorktreeManager(executor)
        for root in roots:
            try:
                worktree_dirs = await manager.list(root)
            except ValueError:
                # ``make_worktree_paths`` rejected the path — old data or
                # operator-edited DB row. Skip rather than blow up.
                logger.warning("Skipping invalid project_root %r", root)
                continue
            for wt_dir in worktree_dirs:
                await self._maybe_remove(session, manager, root, wt_dir, cutoff_ts)

    @staticmethod
    async def _project_roots_for_server(session: AsyncSession, server_id: int) -> list[str]:
        """Distinct base_clone_path values from runs that used the worktree strategy.

        Falls back to scanning ``workspace_path`` ancestors when a run's
        workspace_result doesn't carry the base-clone hint (older runs).
        """
        result = await session.execute(
            select(TaskRun.workspace_result, TaskRun.workspace_path).where(
                TaskRun.workspace_server_id == server_id
            )
        )
        roots: set[str] = set()
        for ws_result, ws_path in result.all():
            if isinstance(ws_result, dict):
                base = ws_result.get("base_clone_path")
                if isinstance(base, str) and base.startswith("/"):
                    roots.add(base.rstrip("/"))
                    continue
            # Heuristic fallback: derive the root from a worktree-style
            # workspace_path like ``/foo/.worktrees/run-7-100`` → ``/foo``.
            if isinstance(ws_path, str) and "/.worktrees/" in ws_path:
                base = ws_path.split("/.worktrees/", 1)[0]
                if base.startswith("/"):
                    roots.add(base)
        return sorted(roots)

    async def _maybe_remove(
        self,
        session: AsyncSession,
        manager: WorktreeManager,
        project_root: str,
        worktree_dir: str,
        cutoff_ts: int,
    ) -> None:
        """Decide+remove one candidate. Caller already filtered base repo."""
        name = PurePosixPath(worktree_dir).name
        match = _WORKTREE_NAME_RE.match(name)
        if not match:
            # Could be the base repo itself (``project_root``) or an
            # operator-created worktree. Don't touch.
            return
        ts = int(match.group("ts"))
        if ts > cutoff_ts:
            return  # still within retention window
        run_id = int(match.group("run_id"))
        run = await session.get(TaskRun, run_id)
        # When the TaskRun is gone (CASCADE delete or manual cleanup) the
        # worktree is by definition an orphan — treat as terminal.
        in_terminal = run is None or str(run.status) in _TERMINAL_STATUSES
        if not in_terminal:
            return

        # Reconstruct the branch from naming convention. The worktree
        # might not actually be on this branch anymore (operator
        # checkout), but ``branch -D`` is best-effort anyway.
        paths = WorktreePaths(
            branch=f"run/{run_id}-{ts}",
            worktree_dir=worktree_dir,
            project_root=project_root,
        )
        logger.info(
            "Removing orphaned worktree %s (run=%d, age>%d days)",
            worktree_dir,
            run_id,
            self._retention_days,
        )
        await manager.remove(paths)
