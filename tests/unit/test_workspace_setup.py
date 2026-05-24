# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for workspace_setup phase."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.worker.phases import workspace_setup


def _mock_server():
    """Return a mock WorkspaceServer with workspace_root."""
    server = MagicMock()
    server.workspace_root = "/home/workspace"
    server.worker_user = "coder"
    server.username = "root"
    return server


def _mock_ssh():
    """Return a mock SSHService with async run_command."""
    ssh = MagicMock()
    ssh.run_command = AsyncMock(return_value=("", "", 0))
    ssh.hostname = "test-host"
    ssh.port = 22
    ssh.username = "root"
    return ssh


def _ws_patches():
    """Common patches for workspace_setup tests."""
    mock_server = _mock_server()
    mock_ssh_instance = _mock_ssh()
    return (
        patch(
            "backend.worker.phases.workspace_setup.get_workspace_server",
            new=AsyncMock(return_value=mock_server),
        ),
        patch(
            "backend.worker.phases.workspace_setup.executor_for_server",
            return_value=mock_ssh_instance,
        ),
        patch(
            "backend.worker.phases.workspace_setup.RemoteGitOps",
        ),
        patch(
            "backend.worker.phases.workspace_setup.RemoteSandbox",
        ),
        patch(
            "backend.worker.phases.workspace_setup.broadcaster",
            new=MagicMock(log=AsyncMock(), event=AsyncMock()),
        ),
        patch(
            "backend.worker.phases.workspace_setup.get_auth_url",
            new=AsyncMock(return_value=("https://authed@url", "https")),
        ),
        patch(
            "backend.worker.phases.workspace_setup.get_project_token",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "backend.worker.phases.workspace_setup._validate_readiness",
            new=AsyncMock(),
        ),
    )


class TestWorkspaceSetup:
    @pytest.fixture(autouse=True)
    async def _project_parent(self, db_session):
        """All tests use proj-1 by default; create the FK parent once per test."""
        from backend.models import ProjectConfig

        db_session.add(
            ProjectConfig(
                project_id="proj-1",
                project_slug="x",
                repo_owner="o",
                repo_name="r",
            )
        )
        await db_session.commit()

    async def test_existing_workspace_already_cloned(
        self, db_session, make_task_run, mock_services
    ):
        """When base repo exists, fetch/reset then cp -a to run workspace."""
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_gitops, p_token, p_ready = _ws_patches()
        with (
            p_server,
            p_ssh as mock_ssh_cls,
            p_git as mock_git_cls,
            p_sandbox,
            p_bc,
            p_gitops,
            p_token,
            p_ready,
        ):
            mock_ssh_instance = mock_ssh_cls.for_server.return_value
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.has_repo = AsyncMock(return_value=True)
            mock_remote_git.run_git = AsyncMock()
            mock_remote_git.clone = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            # Base repo should be fetched/reset, not cloned
            base = "/workspaces/ws"
            git_calls = [
                (c.args[0], c.kwargs.get("cwd")) for c in mock_remote_git.run_git.call_args_list
            ]
            assert (["fetch", "origin"], base) in git_calls
            assert (["checkout", "-f", "main"], base) in git_calls
            assert (["reset", "--hard", "origin/main"], base) in git_calls
            assert (["clean", "-fd"], base) in git_calls
            mock_remote_git.clone.assert_not_called()

            # No per-run copy — workspace used directly
            ssh_cmds = [c.args[0] for c in mock_ssh_instance.run_command.call_args_list]
            cp_cmds = [c for c in ssh_cmds if "cp -a" in c]
            assert len(cp_cmds) == 0
            assert run.workspace_result is not None

    async def test_existing_workspace_needs_clone(self, db_session, make_task_run, mock_services):
        """When repo not on server yet, clone directly to workspace."""
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth, p_token, p_ready = _ws_patches()
        with (
            p_server,
            p_ssh as mock_ssh_cls,
            p_git as mock_git_cls,
            p_sandbox,
            p_bc,
            p_auth,
            p_token,
            p_ready,
        ):
            mock_ssh_instance = mock_ssh_cls.for_server.return_value
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.has_repo = AsyncMock(return_value=False)
            mock_remote_git.pull = AsyncMock()
            mock_remote_git.clone = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            # Clone goes directly to workspace
            clone_call = mock_remote_git.clone.call_args
            assert clone_call.args[1] == "/workspaces/ws"
            mock_remote_git.pull.assert_not_called()

            # No per-run copy — workspace used directly
            ssh_cmds = [c.args[0] for c in mock_ssh_instance.run_command.call_args_list]
            cp_cmds = [c for c in ssh_cmds if "cp -a" in c]
            assert len(cp_cmds) == 0
            assert run.workspace_result is not None

    async def test_relative_path_resolved_to_absolute(
        self, db_session, make_task_run, mock_services
    ):
        """Relative workspace_path gets workspace_root prepended."""
        run = make_task_run(
            workspace_path="myproject",
            workspace_config={"workspace_type": "existing"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth, p_token, p_ready = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_auth, p_token, p_ready:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.has_repo = AsyncMock(return_value=True)
            mock_remote_git.run_git = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            assert run.workspace_path == "/home/workspace/myproject"
            git_calls = [c.args[0] for c in mock_remote_git.run_git.call_args_list]
            assert ["checkout", "-f", "main"] in git_calls

    async def test_cluster_workspace(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={
                "workspace_type": "cluster",
                "repos": [{"url": "https://example.com/repo.git"}],
            },
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth, p_token, p_ready = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_auth, p_token, p_ready:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.clone_or_pull = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            mock_remote_git.clone_or_pull.assert_called_once()

    async def test_cluster_without_repos_raises(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "cluster", "repos": []},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_gitops, p_token, p_ready = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_gitops, p_token, p_ready:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            with pytest.raises(ValueError, match="at least one repo"):
                await workspace_setup.run(run, db_session, mock_services)

    async def test_unknown_workspace_type_raises(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "magic"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_gitops, p_token, p_ready = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_gitops, p_token, p_ready:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            with pytest.raises(ValueError, match="Unknown workspace_type"):
                await workspace_setup.run(run, db_session, mock_services)

    async def test_worktree_strategy_creates_worktree_and_mutates_workspace_path(
        self, db_session, make_task_run, mock_services
    ):
        """With strategy=worktree, workspace_path + branch_name point at the new worktree."""
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing", "strategy": "worktree"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth, p_token, p_ready = _ws_patches()
        with (
            p_server,
            p_ssh,
            p_git as mock_git_cls,
            p_sandbox,
            p_bc,
            p_auth,
            p_token,
            p_ready,
            patch("backend.worker.phases.workspace_setup.WorktreeManager") as mock_wm_cls,
            patch("backend.worker.phases.workspace_setup.make_worktree_paths") as mock_make_paths,
        ):
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.has_repo = AsyncMock(return_value=True)
            mock_remote_git.run_git = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            # Simulate make_worktree_paths returning a deterministic dataclass.
            from backend.services.workspace.worktree import WorktreePaths

            paths = WorktreePaths(
                branch="run/123-1700000000",
                worktree_dir="/workspaces/ws/.worktrees/run-123-1700000000",
                project_root="/workspaces/ws",
            )
            mock_make_paths.return_value = paths

            mock_wm = mock_wm_cls.return_value
            mock_wm.create = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            mock_wm.create.assert_awaited_once_with(paths)
            assert run.workspace_path == "/workspaces/ws/.worktrees/run-123-1700000000"
            assert run.branch_name == "run/123-1700000000"
            assert run.workspace_result is not None
            assert run.workspace_result["base_clone_path"] == "/workspaces/ws"
            assert (
                run.workspace_result["workspace_path"]
                == "/workspaces/ws/.worktrees/run-123-1700000000"
            )
            assert run.workspace_result["worktree_paths"] == {
                "branch": paths.branch,
                "worktree_dir": paths.worktree_dir,
                "project_root": paths.project_root,
            }

    async def test_default_strategy_does_not_create_worktree(
        self, db_session, make_task_run, mock_services
    ):
        """Without strategy=worktree (default), WorktreeManager is never invoked."""
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing"},
        )
        original_branch = run.branch_name
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth, p_token, p_ready = _ws_patches()
        with (
            p_server,
            p_ssh,
            p_git as mock_git_cls,
            p_sandbox,
            p_bc,
            p_auth,
            p_token,
            p_ready,
            patch("backend.worker.phases.workspace_setup.WorktreeManager") as mock_wm_cls,
        ):
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.has_repo = AsyncMock(return_value=True)
            mock_remote_git.run_git = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            # WorktreeManager never instantiated -> no constructor call.
            mock_wm_cls.assert_not_called()
            # branch_name + workspace_path unchanged from the original clone path.
            assert run.workspace_path == "/workspaces/ws"
            assert run.branch_name == original_branch
            assert "worktree_paths" not in (run.workspace_result or {})

    async def test_cluster_with_sandbox(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={
                "workspace_type": "cluster",
                "repos": [{"url": "https://example.com/repo.git"}],
                "sandbox": {"template": "php", "http_port": 9090},
            },
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth, p_token, p_ready = _ws_patches()
        with (
            p_server,
            p_ssh,
            p_git as mock_git_cls,
            p_sandbox as mock_sb_cls,
            p_bc,
            p_auth,
            p_token,
            p_ready,
        ):
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.clone_or_pull = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            mock_remote_sb = mock_sb_cls.return_value
            mock_remote_sb.start_sandbox = AsyncMock(return_value=(True, "http://host:9090"))

            await workspace_setup.run(run, db_session, mock_services)

            mock_remote_sb.start_sandbox.assert_called_once()

    async def test_local_path_skips_clone(self, db_session, make_task_run, mock_services):
        """Project with ``local_path`` set: no clone runs; workspace points at the path."""
        from backend.models import ProjectConfig

        # Replace the autouse-fixture's parent with one that has local_path set.
        existing = await db_session.get(ProjectConfig, "proj-1")
        existing.local_path = "/home/domas/projects/myapp"
        await db_session.commit()

        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth, p_token, p_ready = _ws_patches()
        with (
            p_server,
            p_ssh,
            p_git as mock_git_cls,
            p_sandbox,
            p_bc,
            p_auth,
            p_token,
            p_ready,
            patch(
                "backend.worker.phases.workspace_setup.validate_local_path",
                new=AsyncMock(
                    return_value=MagicMock(
                        path="/home/domas/projects/myapp",
                        exists=True,
                        is_git_repo=True,
                        is_clean=True,
                    )
                ),
            ),
            patch(
                "backend.worker.phases.workspace_setup.make_worktree_paths",
                return_value=MagicMock(
                    branch="run/1-123",
                    worktree_dir="/home/domas/projects/myapp/.worktrees/run-1-123",
                    project_root="/home/domas/projects/myapp",
                ),
            ),
            patch(
                "backend.worker.phases.workspace_setup.WorktreeManager",
            ) as mock_wm_cls,
        ):
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.has_repo = AsyncMock(return_value=True)
            mock_remote_git.run_git = AsyncMock()
            mock_remote_git.clone = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()
            mock_wm_cls.return_value.create = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            # No clone, no fetch — local_path short-circuits both.
            mock_remote_git.clone.assert_not_called()
            mock_remote_git.run_git.assert_not_called()
            # Worktree strategy auto-forced — manager.create was invoked.
            mock_wm_cls.return_value.create.assert_awaited_once()
            # Run now points at the worktree dir under local_path.
            assert run.workspace_path == "/home/domas/projects/myapp/.worktrees/run-1-123"

    async def test_local_path_dirty_raises_before_side_effects(
        self, db_session, make_task_run, mock_services
    ):
        """Dirty working tree → LocalPathError propagates and no clone runs."""
        from backend.models import ProjectConfig
        from backend.services.workspace.local_path import LocalPathError

        existing = await db_session.get(ProjectConfig, "proj-1")
        existing.local_path = "/home/domas/projects/dirty"
        await db_session.commit()

        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth, p_token, p_ready = _ws_patches()
        with (
            p_server,
            p_ssh,
            p_git as mock_git_cls,
            p_sandbox,
            p_bc,
            p_auth,
            p_token,
            p_ready,
            patch(
                "backend.worker.phases.workspace_setup.validate_local_path",
                new=AsyncMock(side_effect=LocalPathError("uncommitted changes — commit or stash")),
            ),
        ):
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.clone = AsyncMock()
            mock_remote_git.run_git = AsyncMock()
            mock_remote_git._mark_safe_directory = AsyncMock()

            with pytest.raises(LocalPathError, match="uncommitted changes"):
                await workspace_setup.run(run, db_session, mock_services)

            mock_remote_git.clone.assert_not_called()
            mock_remote_git.run_git.assert_not_called()
