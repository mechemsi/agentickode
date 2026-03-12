# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for coding phase."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.git.remote_ops import GitResult
from backend.services.role_resolver import ResolvedRole
from backend.worker.phases import coding


class TestCoding:
    async def test_executes_subtasks(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            planning_result={
                "subtasks": [
                    {"title": "Task A", "description": "Do A", "files_likely_affected": ["a.py"]},
                    {"title": "Task B", "description": "Do B", "files_likely_affected": ["b.py"]},
                ]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/openhands"
        mock_adapter.run_task.return_value = {
            "files_changed": ["a.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
            "command": "cd /ws && claude --print",
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.worker.phases.coding._auto_commit_changes",
                new=AsyncMock(return_value=False),
            ),
        ):
            await coding.run(
                run,
                db_session,
                mock_services,
                phase_config={"params": {"subtask_mode": "separate"}},
            )

        assert mock_adapter.run_task.call_count == 2
        assert len(run.coding_results["results"]) == 2

    async def test_no_subtasks_no_title(self, db_session, make_task_run, mock_services):
        run = make_task_run(planning_result={"subtasks": []}, title="")
        db_session.add(run)
        await db_session.commit()

        with patch(
            "backend.worker.phases.coding.broadcaster",
            new=MagicMock(log=AsyncMock(), event=AsyncMock()),
        ):
            await coding.run(run, db_session, mock_services)

        assert run.coding_results == {"results": []}
        # role_resolver should not be called when there are no subtasks and no title
        mock_services.role_resolver.resolve.assert_not_called()

    async def test_resolves_coder_role(self, db_session, make_task_run, mock_services):
        """Verifies the coder role is resolved through role_resolver."""
        run = make_task_run(
            planning_result={
                "subtasks": [{"title": "T", "description": "D", "files_likely_affected": []}]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws-01"
        mock_adapter.run_task.return_value = {
            "files_changed": ["f.py"],
            "exit_code": 0,
            "output": "",
            "stderr": "",
            "command": "cd /ws && claude --print",
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=5),
            ),
        ):
            await coding.run(run, db_session, mock_services)

        mock_services.role_resolver.resolve.assert_called_once_with(
            "coder", db_session, 5, phase_name="coding"
        )

    async def test_fails_when_all_subtasks_fail(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            planning_result={
                "subtasks": [
                    {"title": "T1", "description": "D1", "files_likely_affected": []},
                ]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws"
        mock_adapter.run_task.return_value = {
            "files_changed": [],
            "exit_code": 1,
            "output": "",
            "stderr": "error",
            "command": "cd /ws && claude",
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
            pytest.raises(RuntimeError, match="All 1 subtask"),
        ):
            await coding.run(run, db_session, mock_services)

    async def test_fails_when_no_files_changed(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            planning_result={
                "subtasks": [
                    {"title": "T1", "description": "D1", "files_likely_affected": []},
                ]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws"
        mock_adapter.run_task.return_value = {
            "files_changed": [],
            "exit_code": 0,
            "output": "ok",
            "stderr": "",
            "command": "cd /ws && claude",
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
            pytest.raises(RuntimeError, match="no file changes"),
        ):
            await coding.run(run, db_session, mock_services)

    async def test_auto_commits_uncommitted_changes(self, db_session, make_task_run, mock_services):
        """After each subtask, uncommitted changes are auto-committed."""
        run = make_task_run(
            planning_result={
                "subtasks": [
                    {"title": "Add login", "description": "D", "files_likely_affected": []},
                ]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws"
        mock_adapter.run_task.return_value = {
            "files_changed": ["login.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
            "command": "cd /ws && claude",
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        mock_ssh = MagicMock()
        mock_remote_git = MagicMock()
        mock_remote_git._mark_safe_directory = AsyncMock()
        mock_remote_git.run_git = AsyncMock(
            side_effect=[
                # git status --porcelain → has changes
                GitResult(stdout=" M login.py\n", stderr=""),
                # git add -A
                GitResult(stdout="", stderr=""),
                # git commit
                GitResult(stdout="", stderr=""),
            ]
        )

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.worker.phases.coding.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch(
                "backend.worker.phases.coding.RemoteGitOps",
                return_value=mock_remote_git,
            ),
        ):
            await coding.run(run, db_session, mock_services)

        # Verify git add + commit were called
        git_calls = [c.args[0] for c in mock_remote_git.run_git.call_args_list]
        assert ["status", "--porcelain"] in git_calls
        assert ["add", "-A"] in git_calls
        assert any("commit" in call[0] for call in git_calls)

    async def test_auto_commit_skipped_when_clean(self, db_session, make_task_run, mock_services):
        """Auto-commit is skipped when there are no uncommitted changes."""
        run = make_task_run(
            planning_result={
                "subtasks": [
                    {"title": "T", "description": "D", "files_likely_affected": []},
                ]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws"
        mock_adapter.run_task.return_value = {
            "files_changed": ["f.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
            "command": "cd /ws && claude",
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        mock_ssh = MagicMock()
        mock_remote_git = MagicMock()
        mock_remote_git._mark_safe_directory = AsyncMock()
        mock_remote_git.run_git = AsyncMock(
            return_value=GitResult(stdout="", stderr=""),  # clean status
        )

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.worker.phases.coding.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch(
                "backend.worker.phases.coding.RemoteGitOps",
                return_value=mock_remote_git,
            ),
        ):
            await coding.run(run, db_session, mock_services)

        # Only status check should be called, not add/commit
        git_calls = [c.args[0] for c in mock_remote_git.run_git.call_args_list]
        assert ["status", "--porcelain"] in git_calls
        assert ["add", "-A"] not in git_calls