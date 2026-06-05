# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for finalization phase."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.worker.phases import finalization


class TestFinalization:
    @pytest.fixture(autouse=True)
    async def _project_parent(self, db_session):
        """All tests use proj-1; create the FK parent once per test."""
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

    async def test_logs_pr_url_and_cleans_up(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            pr_url="https://gitea.test/org/repo/pulls/1",
        )
        db_session.add(run)
        await db_session.commit()

        mock_broadcaster = MagicMock(log=AsyncMock(), event=AsyncMock())

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=mock_broadcaster,
            ),
        ):
            mock_remote_sb = mock_sb_cls.return_value
            mock_remote_sb.stop_sandbox = AsyncMock()

            await finalization.run(run, db_session, mock_services)

        # Should log PR URL, not merge it
        log_messages = [call.args[1] for call in mock_broadcaster.log.call_args_list]
        assert any("PR ready for human review" in m for m in log_messages)
        mock_remote_sb.stop_sandbox.assert_called_once_with(run.workspace_path)

    async def test_no_pr_url_warns(self, db_session, make_task_run, mock_services):
        run = make_task_run(pr_url=None)
        db_session.add(run)
        await db_session.commit()

        mock_broadcaster = MagicMock(log=AsyncMock(), event=AsyncMock())

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=mock_broadcaster,
            ),
        ):
            mock_remote_sb = mock_sb_cls.return_value
            mock_remote_sb.stop_sandbox = AsyncMock()

            await finalization.run(run, db_session, mock_services)

        log_messages = [call.args[1] for call in mock_broadcaster.log.call_args_list]
        assert any("No PR URL" in m for m in log_messages)

    async def test_cleanup_error_propagates(self, db_session, make_task_run, mock_services):
        """Sandbox cleanup errors currently propagate (not silently ignored)."""
        run = make_task_run(pr_url="https://gitea.test/org/repo/pulls/2")
        db_session.add(run)
        await db_session.commit()

        import pytest

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
        ):
            mock_remote_sb = mock_sb_cls.return_value
            mock_remote_sb.stop_sandbox = AsyncMock(side_effect=Exception("cleanup failed"))

            with pytest.raises(Exception, match="cleanup failed"):
                await finalization.run(run, db_session, mock_services)

    async def test_task_scoped_workspace_deleted_on_finalization(
        self, db_session, make_task_run, mock_services
    ):
        """Task-scoped workspace path (ending with /{run.id}) is removed via SSH."""
        run = make_task_run(pr_url="https://gitea.test/org/repo/pulls/3")
        db_session.add(run)
        await db_session.commit()

        # Set workspace_path to a task-scoped path matching the run's id
        run.workspace_path = f"/home/worker/workspaces/my-repo/{run.id}"

        mock_ssh = AsyncMock()
        mock_ssh.run_command = AsyncMock(return_value=("", "", 0))

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
        ):
            mock_remote_sb = mock_sb_cls.return_value
            mock_remote_sb.stop_sandbox = AsyncMock()

            await finalization.run(run, db_session, mock_services)

        # Verify rm -rf was called with the task-scoped path
        mock_ssh.run_command.assert_called_once()
        cmd_arg = mock_ssh.run_command.call_args.args[0]
        assert "rm -rf" in cmd_arg
        assert str(run.id) in cmd_arg

    async def test_worktree_removed_when_workspace_result_has_paths(
        self, db_session, make_task_run, mock_services
    ):
        """worktree_paths in workspace_result triggers WorktreeManager.remove()."""
        run = make_task_run(pr_url="https://gitea.test/org/repo/pulls/5")
        run.workspace_result = {
            "workspace_path": "/srv/repo/.worktrees/run-99-100",
            "base_clone_path": "/srv/repo",
            "worktree_paths": {
                "branch": "run/99-100",
                "worktree_dir": "/srv/repo/.worktrees/run-99-100",
                "project_root": "/srv/repo",
            },
        }
        db_session.add(run)
        await db_session.commit()

        mock_ssh = AsyncMock()
        mock_ssh.run_command = AsyncMock(return_value=("", "", 0))

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.WorktreeManager") as mock_wm_cls,
        ):
            mock_sb_cls.return_value.stop_sandbox = AsyncMock()
            mock_wm = mock_wm_cls.return_value
            mock_wm.remove = AsyncMock()

            await finalization.run(run, db_session, mock_services)

            mock_wm.remove.assert_awaited_once()
            removed_paths = mock_wm.remove.call_args.args[0]
            assert removed_paths.worktree_dir == "/srv/repo/.worktrees/run-99-100"
            assert removed_paths.branch == "run/99-100"

    async def test_worktree_kept_when_keep_workspace_true(
        self, db_session, make_task_run, mock_services
    ):
        """phase_config.keep_workspace=True preserves the worktree."""
        run = make_task_run(pr_url="https://gitea.test/org/repo/pulls/6")
        run.workspace_result = {
            "workspace_path": "/srv/repo/.worktrees/run-100-200",
            "worktree_paths": {
                "branch": "run/100-200",
                "worktree_dir": "/srv/repo/.worktrees/run-100-200",
                "project_root": "/srv/repo",
            },
        }
        db_session.add(run)
        await db_session.commit()

        mock_ssh = AsyncMock()
        mock_ssh.run_command = AsyncMock(return_value=("", "", 0))

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.WorktreeManager") as mock_wm_cls,
        ):
            mock_sb_cls.return_value.stop_sandbox = AsyncMock()

            await finalization.run(
                run, db_session, mock_services, phase_config={"keep_workspace": True}
            )

            mock_wm_cls.assert_not_called()

    async def test_worktree_cleanup_error_swallowed(self, db_session, make_task_run, mock_services):
        """A failing worktree remove must not break finalization."""
        run = make_task_run(pr_url="https://gitea.test/org/repo/pulls/7")
        run.workspace_result = {
            "worktree_paths": {
                "branch": "run/101-300",
                "worktree_dir": "/srv/repo/.worktrees/run-101-300",
                "project_root": "/srv/repo",
            },
        }
        db_session.add(run)
        await db_session.commit()

        mock_ssh = AsyncMock()
        mock_ssh.run_command = AsyncMock(return_value=("", "", 0))

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.WorktreeManager") as mock_wm_cls,
        ):
            mock_sb_cls.return_value.stop_sandbox = AsyncMock()
            mock_wm_cls.return_value.remove = AsyncMock(side_effect=RuntimeError("git died"))

            # Should NOT raise — finalization continues.
            await finalization.run(run, db_session, mock_services)

    async def test_review_comment_mode_does_not_push_branch(
        self, db_session, make_task_run, mock_services
    ):
        """A comment-mode PR review must post the review but never push to the PR branch."""
        run = make_task_run(
            pr_url=None,
            task_source_meta={
                "pr_head_branch": "feature/x",
                "pr_number": 7,
                "review_mode": "comment",
            },
            review_result={"approved": False, "issues": [{"severity": "major"}]},
        )
        db_session.add(run)
        await db_session.commit()

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.finalization._push_to_pr_branch",
                new=AsyncMock(),
            ) as mock_push,
            patch(
                "backend.worker.phases.finalization._post_review_comment",
                new=AsyncMock(),
            ) as mock_comment,
        ):
            mock_sb_cls.return_value.stop_sandbox = AsyncMock()
            await finalization.run(run, db_session, mock_services)

        mock_push.assert_not_called()
        mock_comment.assert_awaited_once()
        assert mock_comment.call_args.args[1] == 7

    async def test_comment_mode_skips_workspace_cleanup(
        self, db_session, make_task_run, mock_services
    ):
        """A comment-mode review creates no workspace, so finalization skips SSH cleanup."""
        run = make_task_run(
            pr_url=None,
            task_source_meta={"pr_number": 9, "review_mode": "comment"},
            review_result={"approved": True, "issues": []},
        )
        db_session.add(run)
        await db_session.commit()

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=AsyncMock()),
            ) as mock_ssh,
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.finalization._post_review_comment",
                new=AsyncMock(),
            ) as mock_comment,
        ):
            await finalization.run(run, db_session, mock_services)

        mock_comment.assert_awaited_once()
        mock_sb_cls.assert_not_called()  # no sandbox stop
        mock_ssh.assert_not_called()  # no SSH cleanup at all

    async def test_fix_mode_pushes_to_pr_branch(self, db_session, make_task_run, mock_services):
        """An explicit fix-mode run pushes fixes to the existing PR branch."""
        run = make_task_run(
            pr_url=None,
            task_source_meta={"pr_head_branch": "feature/x", "review_mode": "fix"},
        )
        db_session.add(run)
        await db_session.commit()

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=AsyncMock()),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.finalization._push_to_pr_branch",
                new=AsyncMock(),
            ) as mock_push,
        ):
            mock_sb_cls.return_value.stop_sandbox = AsyncMock()
            await finalization.run(run, db_session, mock_services)

        mock_push.assert_awaited_once()

    async def test_shared_workspace_not_deleted(self, db_session, make_task_run, mock_services):
        """Workspace paths that don't end with /{run.id} are not deleted."""
        run = make_task_run(pr_url="https://gitea.test/org/repo/pulls/4")
        db_session.add(run)
        await db_session.commit()

        # workspace_path does NOT end with /{run.id} — shared path
        run.workspace_path = "/home/worker/workspaces/my-repo"

        mock_ssh = AsyncMock()
        mock_ssh.run_command = AsyncMock(return_value=("", "", 0))

        with (
            patch(
                "backend.worker.phases.finalization.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch("backend.worker.phases.finalization.RemoteSandbox") as mock_sb_cls,
            patch(
                "backend.worker.phases.finalization.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
        ):
            mock_remote_sb = mock_sb_cls.return_value
            mock_remote_sb.stop_sandbox = AsyncMock()

            await finalization.run(run, db_session, mock_services)

        # rm -rf should NOT have been called for a shared path
        mock_ssh.run_command.assert_not_called()
