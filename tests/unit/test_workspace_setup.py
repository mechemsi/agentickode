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
    return server


def _ws_patches():
    """Common patches for workspace_setup tests."""
    mock_server = _mock_server()
    return (
        patch(
            "backend.worker.phases.workspace_setup.get_workspace_server",
            new=AsyncMock(return_value=mock_server),
        ),
        patch(
            "backend.worker.phases.workspace_setup.SSHService",
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
    )


class TestWorkspaceSetup:
    async def test_existing_workspace_already_cloned(
        self, db_session, make_task_run, mock_services
    ):
        """When repo already exists on server, reset to default branch and pull."""
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_gitops = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_gitops:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.has_repo = AsyncMock(return_value=True)
            mock_remote_git.run_git = AsyncMock()
            mock_remote_git.clone = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            # Should checkout -f, clean, and pull via run_git — not clone
            git_calls = [c.args[0] for c in mock_remote_git.run_git.call_args_list]
            assert ["checkout", "-f", "main"] in git_calls
            assert ["clean", "-fd"] in git_calls
            assert ["pull", "origin", "main"] in git_calls
            mock_remote_git.clone.assert_not_called()
            assert run.workspace_result is not None

    async def test_existing_workspace_needs_clone(self, db_session, make_task_run, mock_services):
        """When repo not on server yet, clone with credentials."""
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "existing"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_auth:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.has_repo = AsyncMock(return_value=False)
            mock_remote_git.pull = AsyncMock()
            mock_remote_git.clone = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            mock_remote_git.clone.assert_called_once()
            mock_remote_git.pull.assert_not_called()
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

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_auth:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.has_repo = AsyncMock(return_value=True)
            mock_remote_git.run_git = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            # Path should be resolved to /home/workspace/myproject
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

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_auth:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.clone_or_pull = AsyncMock()

            await workspace_setup.run(run, db_session, mock_services)

            mock_remote_git.clone_or_pull.assert_called_once()

    async def test_cluster_without_repos_raises(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "cluster", "repos": []},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_gitops = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_gitops:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()

            with pytest.raises(ValueError, match="at least one repo"):
                await workspace_setup.run(run, db_session, mock_services)

    async def test_unknown_workspace_type_raises(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            workspace_path="/workspaces/ws",
            workspace_config={"workspace_type": "magic"},
        )
        db_session.add(run)
        await db_session.commit()

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_gitops = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox, p_bc, p_gitops:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()

            with pytest.raises(ValueError, match="Unknown workspace_type"):
                await workspace_setup.run(run, db_session, mock_services)

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

        p_server, p_ssh, p_git, p_sandbox, p_bc, p_auth = _ws_patches()
        with p_server, p_ssh, p_git as mock_git_cls, p_sandbox as mock_sb_cls, p_bc, p_auth:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.mkdir = AsyncMock()
            mock_remote_git.clone_or_pull = AsyncMock()

            mock_remote_sb = mock_sb_cls.return_value
            mock_remote_sb.start_sandbox = AsyncMock(return_value=(True, "http://host:9090"))

            await workspace_setup.run(run, db_session, mock_services)

            mock_remote_sb.start_sandbox.assert_called_once()