# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for WorktreeCleanupScheduler."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models import ProjectConfig, WorkspaceServer
from backend.worker.worktree_cleanup_scheduler import WorktreeCleanupScheduler


@pytest.fixture()
async def session_factory(db_session):
    """Return a no-op factory that hands out the test session via async ctx."""

    class _SessionCtx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _factory():
        return _SessionCtx()

    return _factory


@pytest.fixture(autouse=True)
async def _project_parent(db_session):
    db_session.add(
        ProjectConfig(
            project_id="proj-1",
            project_slug="x",
            repo_owner="o",
            repo_name="r",
        )
    )
    await db_session.commit()


async def _make_server(db_session, **overrides) -> WorkspaceServer:
    server = WorkspaceServer(
        name=overrides.get("name", "test-server"),
        hostname="localhost",
        port=22,
        username="root",
        server_type="local",
        workspace_root="/srv/repos",
        worker_user="coder",
        max_concurrent_tasks=1,
    )
    for k, v in overrides.items():
        setattr(server, k, v)
    db_session.add(server)
    await db_session.commit()
    return server


async def _make_run(
    db_session,
    make_task_run,
    *,
    server_id: int,
    status: str,
    base_clone_path: str,
    workspace_path: str,
) -> None:
    run = make_task_run(
        workspace_path=workspace_path,
        workspace_server_id=server_id,
    )
    run.status = status
    run.workspace_result = {
        "base_clone_path": base_clone_path,
        "workspace_path": workspace_path,
        "worktree_paths": {
            "branch": "run/x-x",
            "worktree_dir": workspace_path,
            "project_root": base_clone_path,
        },
    }
    db_session.add(run)
    await db_session.commit()
    return run


class TestWorktreeCleanupScheduler:
    async def test_removes_old_orphaned_worktree_for_terminal_run(
        self, db_session, make_task_run, session_factory
    ):
        server = await _make_server(db_session)
        # Old timestamp (well before cutoff)
        old_ts = 1_000_000_000
        worktree_dir = f"/srv/repos/foo/.worktrees/run-{0}-{old_ts}"
        # Need a real run.id for the lookup; create with default factory
        # then override status to terminal.
        run = await _make_run(
            db_session,
            make_task_run,
            server_id=server.id,
            status="completed",
            base_clone_path="/srv/repos/foo",
            workspace_path=worktree_dir,
        )
        actual_worktree_dir = f"/srv/repos/foo/.worktrees/run-{run.id}-{old_ts}"

        # Patch the executor + manager so we don't shell out.
        mock_manager = MagicMock()
        mock_manager.list = AsyncMock(return_value=["/srv/repos/foo", actual_worktree_dir])
        mock_manager.remove = AsyncMock()

        with (
            patch(
                "backend.worker.worktree_cleanup_scheduler.executor_for_server",
                return_value=MagicMock(),
            ),
            patch(
                "backend.worker.worktree_cleanup_scheduler.WorktreeManager",
                return_value=mock_manager,
            ),
        ):
            scheduler = WorktreeCleanupScheduler(
                session_factory, poll_seconds=3600, retention_days=7
            )
            await scheduler._tick()

        mock_manager.remove.assert_awaited_once()
        removed = mock_manager.remove.call_args.args[0]
        assert removed.worktree_dir == actual_worktree_dir
        assert removed.project_root == "/srv/repos/foo"
        # Branch name reconstructed from the dir name.
        assert removed.branch == f"run/{run.id}-{old_ts}"

    async def test_skips_recent_worktree_within_retention(
        self, db_session, make_task_run, session_factory
    ):
        server = await _make_server(db_session)
        recent_ts = int(datetime.now(UTC).timestamp())  # now → within window
        worktree_dir = f"/srv/repos/foo/.worktrees/run-1-{recent_ts}"
        run = await _make_run(
            db_session,
            make_task_run,
            server_id=server.id,
            status="completed",
            base_clone_path="/srv/repos/foo",
            workspace_path=worktree_dir,
        )
        actual_worktree_dir = f"/srv/repos/foo/.worktrees/run-{run.id}-{recent_ts}"

        mock_manager = MagicMock()
        mock_manager.list = AsyncMock(return_value=[actual_worktree_dir])
        mock_manager.remove = AsyncMock()

        with (
            patch(
                "backend.worker.worktree_cleanup_scheduler.executor_for_server",
                return_value=MagicMock(),
            ),
            patch(
                "backend.worker.worktree_cleanup_scheduler.WorktreeManager",
                return_value=mock_manager,
            ),
        ):
            scheduler = WorktreeCleanupScheduler(session_factory)
            await scheduler._tick()

        mock_manager.remove.assert_not_awaited()

    async def test_skips_worktree_for_in_flight_run(
        self, db_session, make_task_run, session_factory
    ):
        server = await _make_server(db_session)
        old_ts = 1_000_000_000
        worktree_dir = f"/srv/repos/foo/.worktrees/run-1-{old_ts}"
        run = await _make_run(
            db_session,
            make_task_run,
            server_id=server.id,
            status="running",  # not terminal
            base_clone_path="/srv/repos/foo",
            workspace_path=worktree_dir,
        )
        actual_worktree_dir = f"/srv/repos/foo/.worktrees/run-{run.id}-{old_ts}"

        mock_manager = MagicMock()
        mock_manager.list = AsyncMock(return_value=[actual_worktree_dir])
        mock_manager.remove = AsyncMock()

        with (
            patch(
                "backend.worker.worktree_cleanup_scheduler.executor_for_server",
                return_value=MagicMock(),
            ),
            patch(
                "backend.worker.worktree_cleanup_scheduler.WorktreeManager",
                return_value=mock_manager,
            ),
        ):
            scheduler = WorktreeCleanupScheduler(session_factory)
            await scheduler._tick()

        mock_manager.remove.assert_not_awaited()

    async def test_ignores_non_run_worktree_entries(
        self, db_session, make_task_run, session_factory
    ):
        """The base repo itself + operator-created worktrees are left alone."""
        server = await _make_server(db_session)
        # Seed at least one run so the project root is discovered.
        await _make_run(
            db_session,
            make_task_run,
            server_id=server.id,
            status="completed",
            base_clone_path="/srv/repos/foo",
            workspace_path="/srv/repos/foo/.worktrees/run-1-100",
        )

        mock_manager = MagicMock()
        mock_manager.list = AsyncMock(
            return_value=[
                "/srv/repos/foo",  # base repo
                "/srv/repos/foo/.worktrees/operator-experiment",  # ad-hoc
            ]
        )
        mock_manager.remove = AsyncMock()

        with (
            patch(
                "backend.worker.worktree_cleanup_scheduler.executor_for_server",
                return_value=MagicMock(),
            ),
            patch(
                "backend.worker.worktree_cleanup_scheduler.WorktreeManager",
                return_value=mock_manager,
            ),
        ):
            scheduler = WorktreeCleanupScheduler(session_factory)
            await scheduler._tick()

        mock_manager.remove.assert_not_awaited()

    async def test_no_servers_no_op(self, db_session, session_factory):
        """Empty WorkspaceServer table is fine — tick returns silently."""
        with patch("backend.worker.worktree_cleanup_scheduler.executor_for_server") as ex:
            scheduler = WorktreeCleanupScheduler(session_factory)
            await scheduler._tick()
        ex.assert_not_called()
