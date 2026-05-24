# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for WorktreePaths + WorktreeManager."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.services.workspace.worktree import (
    WorktreeManager,
    WorktreePaths,
    make_worktree_paths,
)


class TestMakeWorktreePaths:
    """``make_worktree_paths`` is pure — exercise the naming contract."""

    def test_produces_expected_branch_and_dir(self):
        paths = make_worktree_paths("/srv/repos/foo", 42)
        assert paths.branch.startswith("run/42-")
        assert paths.worktree_dir.startswith("/srv/repos/foo/.worktrees/run-42-")
        # Branch + dir share the suffix
        suffix = paths.branch.split("-", 1)[1]
        assert paths.worktree_dir.endswith(f"run-42-{suffix}")
        assert paths.project_root == "/srv/repos/foo"

    def test_handles_trailing_slash_on_project_root(self):
        paths = make_worktree_paths("/srv/repos/foo/", 1)
        # No double slash in worktree dir
        assert "//" not in paths.worktree_dir
        assert paths.worktree_dir.startswith("/srv/repos/foo/.worktrees/run-1-")

    def test_two_calls_within_same_second_are_identical(self, monkeypatch):
        # Pin time so the timestamp suffix is stable across calls.
        monkeypatch.setattr(
            "backend.services.workspace.worktree.time.time",
            lambda: 1_700_000_000.0,
        )
        a = make_worktree_paths("/srv/repos/foo", 99)
        b = make_worktree_paths("/srv/repos/foo", 99)
        assert a == b
        assert a.branch == "run/99-1700000000"
        assert a.worktree_dir == "/srv/repos/foo/.worktrees/run-99-1700000000"

    @pytest.mark.parametrize(
        "bad_root",
        [
            "; rm -rf /",
            "../etc",
            "relative/path",
            "/path with spaces/foo",
            "/path/with$shellvar",
            "",
        ],
    )
    def test_rejects_unsafe_project_root(self, bad_root):
        with pytest.raises(ValueError, match="unsafe project_root"):
            make_worktree_paths(bad_root, 1)


def _executor(returns=("", "", 0)):
    ex = AsyncMock()
    ex.run_command = AsyncMock(return_value=returns)
    return ex


class TestWorktreeManagerCreate:
    async def test_runs_git_worktree_add_with_correct_args(self):
        ex = AsyncMock()
        # First call: ``test -d`` — return non-zero (does not exist).
        # Subsequent calls: mkdir then git worktree add — return zero.
        ex.run_command = AsyncMock(
            side_effect=[
                ("", "", 1),  # test -d
                ("", "", 0),  # mkdir -p
                ("Preparing worktree...\n", "", 0),  # git worktree add
            ]
        )
        mgr = WorktreeManager(ex)
        paths = WorktreePaths(
            branch="run/7-100",
            worktree_dir="/srv/foo/.worktrees/run-7-100",
            project_root="/srv/foo",
        )
        await mgr.create(paths)
        # The git command is the third call.
        git_call = ex.run_command.call_args_list[2].args[0]
        assert "git -C /srv/foo worktree add" in git_call
        assert "-b run/7-100" in git_call
        assert "/srv/foo/.worktrees/run-7-100" in git_call

    async def test_idempotent_when_dir_already_exists(self):
        ex = AsyncMock()
        # ``test -d`` succeeds — dir already exists, no further calls.
        ex.run_command = AsyncMock(return_value=("", "", 0))
        mgr = WorktreeManager(ex)
        paths = WorktreePaths(
            branch="run/1-1",
            worktree_dir="/srv/foo/.worktrees/run-1-1",
            project_root="/srv/foo",
        )
        await mgr.create(paths)
        # Exactly one call (the existence probe) — no mkdir, no git add.
        assert ex.run_command.call_count == 1

    async def test_swallows_already_exists_race(self):
        """If another retry created the dir between our probe and ``git add``."""
        ex = AsyncMock()
        ex.run_command = AsyncMock(
            side_effect=[
                ("", "", 1),  # test -d: doesn't exist yet
                ("", "", 0),  # mkdir -p
                ("", "fatal: '...' already exists", 128),  # git worktree add race
            ]
        )
        mgr = WorktreeManager(ex)
        paths = WorktreePaths(
            branch="run/1-1",
            worktree_dir="/srv/foo/.worktrees/run-1-1",
            project_root="/srv/foo",
        )
        await mgr.create(paths)  # does not raise

    async def test_raises_on_unexpected_git_failure(self):
        ex = AsyncMock()
        ex.run_command = AsyncMock(
            side_effect=[
                ("", "", 1),  # test -d
                ("", "", 0),  # mkdir -p
                ("", "fatal: not a git repository", 128),
            ]
        )
        mgr = WorktreeManager(ex)
        paths = WorktreePaths(
            branch="run/1-1",
            worktree_dir="/srv/foo/.worktrees/run-1-1",
            project_root="/srv/foo",
        )
        with pytest.raises(RuntimeError, match="git worktree add failed"):
            await mgr.create(paths)

    async def test_chowns_parent_when_worker_user_set(self):
        ex = AsyncMock()
        ex.run_command = AsyncMock(
            side_effect=[
                ("", "", 1),  # test -d
                ("", "", 0),  # mkdir -p
                ("", "", 0),  # chown
                ("", "", 0),  # git worktree add
            ]
        )
        mgr = WorktreeManager(ex, worker_user="coder")
        paths = WorktreePaths(
            branch="run/1-1",
            worktree_dir="/srv/foo/.worktrees/run-1-1",
            project_root="/srv/foo",
        )
        await mgr.create(paths)
        chown_call = ex.run_command.call_args_list[2].args[0]
        assert chown_call.startswith("chown coder:coder")
        assert "/srv/foo/.worktrees" in chown_call


class TestWorktreeManagerRemove:
    async def test_runs_remove_then_branch_delete(self):
        ex = _executor()
        mgr = WorktreeManager(ex)
        paths = WorktreePaths(
            branch="run/2-2",
            worktree_dir="/srv/foo/.worktrees/run-2-2",
            project_root="/srv/foo",
        )
        await mgr.remove(paths)
        cmds = [c.args[0] for c in ex.run_command.call_args_list]
        assert any("worktree remove --force /srv/foo/.worktrees/run-2-2" in c for c in cmds)
        assert any("branch -D run/2-2" in c for c in cmds)

    async def test_swallows_not_a_working_tree(self):
        ex = AsyncMock()
        ex.run_command = AsyncMock(
            side_effect=[
                ("", "fatal: '...' is not a working tree", 128),
                ("", "", 0),
            ]
        )
        mgr = WorktreeManager(ex)
        paths = WorktreePaths(
            branch="run/3-3",
            worktree_dir="/srv/foo/.worktrees/run-3-3",
            project_root="/srv/foo",
        )
        await mgr.remove(paths)  # does not raise

    async def test_swallows_branch_already_gone(self):
        ex = AsyncMock()
        ex.run_command = AsyncMock(
            side_effect=[
                ("", "", 0),
                ("", "error: branch '...' not found", 1),
            ]
        )
        mgr = WorktreeManager(ex)
        paths = WorktreePaths(
            branch="run/3-3",
            worktree_dir="/srv/foo/.worktrees/run-3-3",
            project_root="/srv/foo",
        )
        await mgr.remove(paths)  # does not raise


class TestWorkspaceSetupFinalizationRoundTrip:
    """End-to-end: workspace_setup creates a worktree, finalization removes it.

    Drives the actual phase functions (not just the manager) to prove the
    `workspace_result['worktree_paths']` shape round-trips through
    `WorktreePaths(**stored)` in finalization without drift.
    """

    async def test_worktree_paths_survive_setup_to_finalization(
        self, db_session, make_task_run, mock_services
    ):
        from unittest.mock import MagicMock, patch

        from backend.models import ProjectConfig
        from backend.worker.phases import finalization, workspace_setup

        db_session.add(
            ProjectConfig(project_id="proj-1", project_slug="x", repo_owner="o", repo_name="r")
        )
        await db_session.commit()

        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing", "strategy": "worktree"},
            pr_url="https://gitea.test/org/repo/pulls/9",
        )
        db_session.add(run)
        await db_session.commit()

        # --- Phase 1: workspace_setup with a real WorktreeManager but a
        #     mocked SSH. The manager builds + records the paths into
        #     task_run.workspace_result.
        server = MagicMock(workspace_root="/home/workspace", worker_user="coder")
        ssh = MagicMock(hostname="h", port=22, username="root")
        ssh.run_command = AsyncMock(return_value=("", "", 0))

        with (
            patch(
                "backend.worker.phases.workspace_setup.get_workspace_server",
                new=AsyncMock(return_value=server),
            ),
            patch(
                "backend.worker.phases.workspace_setup.executor_for_server",
                return_value=ssh,
            ),
            patch("backend.worker.phases.workspace_setup.RemoteGitOps") as mock_git_cls,
            patch("backend.worker.phases.workspace_setup.RemoteSandbox"),
            patch(
                "backend.worker.phases.workspace_setup.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.workspace_setup.get_auth_url",
                new=AsyncMock(return_value=("https://authed", "https")),
            ),
            patch(
                "backend.worker.phases.workspace_setup.get_project_token",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.worker.phases.workspace_setup._validate_readiness",
                new=AsyncMock(),
            ),
        ):
            git = mock_git_cls.return_value
            git.mkdir = AsyncMock()
            git.has_repo = AsyncMock(return_value=True)
            git.run_git = AsyncMock()
            git._mark_safe_directory = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

        # workspace_setup mutated the run + recorded the paths.
        stored = run.workspace_result["worktree_paths"]
        assert run.workspace_path == stored["worktree_dir"]
        assert run.branch_name == stored["branch"]

        # --- Phase 2: finalization rehydrates via WorktreePaths(**stored)
        #     and calls remove. Verify the same dataclass survives the
        #     round-trip without key drift.
        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=ssh),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.WorktreeManager") as mock_wm_cls,
        ):
            mock_sb_cls.return_value.stop_sandbox = AsyncMock()
            mock_wm_cls.return_value.remove = AsyncMock()

            await finalization.run(run, db_session, mock_services)

            removed = mock_wm_cls.return_value.remove.call_args.args[0]
            # Same triple emerges on the other side.
            assert removed.branch == stored["branch"]
            assert removed.worktree_dir == stored["worktree_dir"]
            assert removed.project_root == stored["project_root"]


class TestWorktreeManagerList:
    async def test_parses_porcelain_output(self):
        porcelain = (
            "worktree /srv/foo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /srv/foo/.worktrees/run-1-100\n"
            "HEAD def456\n"
            "branch refs/heads/run/1-100\n"
            "\n"
            "worktree /srv/foo/.worktrees/run-2-200\n"
            "HEAD ghi789\n"
            "branch refs/heads/run/2-200\n"
        )
        ex = _executor((porcelain, "", 0))
        mgr = WorktreeManager(ex)
        dirs = await mgr.list("/srv/foo")
        assert dirs == [
            "/srv/foo",
            "/srv/foo/.worktrees/run-1-100",
            "/srv/foo/.worktrees/run-2-200",
        ]

    async def test_returns_empty_on_failure(self):
        ex = _executor(("", "fatal: not a git repo", 128))
        mgr = WorktreeManager(ex)
        assert await mgr.list("/srv/foo") == []

    async def test_rejects_unsafe_root(self):
        ex = _executor()
        mgr = WorktreeManager(ex)
        with pytest.raises(ValueError, match="unsafe project_root"):
            await mgr.list("../etc")
