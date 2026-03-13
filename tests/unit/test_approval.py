# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for approval phase."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.worker.phases import approval


def _git_result(stdout: str = "", stderr: str = "") -> MagicMock:
    """Return a mock GitResult with stdout/stderr."""
    r = MagicMock()
    r.stdout = stdout
    r.stderr = stderr
    return r


def _approval_patches():
    """Common patches for approval phase tests."""
    return {
        "get_git_provider": patch("backend.worker.phases.approval.get_git_provider"),
        "get_auth_url": patch(
            "backend.worker.phases.approval.get_auth_url",
            new=AsyncMock(return_value=("https://token@gitea.test/org/repo.git", "https")),
        ),
        "get_ssh_for_run": patch(
            "backend.worker.phases.approval.get_ssh_for_run",
            new=AsyncMock(return_value=AsyncMock()),
        ),
        "RemoteGitOps": patch("backend.worker.phases.approval.RemoteGitOps"),
        "broadcaster": patch(
            "backend.worker.phases.approval.broadcaster",
            new=MagicMock(log=AsyncMock(), event=AsyncMock()),
        ),
    }


class TestApproval:
    async def test_pushes_and_creates_pr(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            review_result={"approved": True, "issues": [], "suggestions": ["test it"]},
        )
        db_session.add(run)
        await db_session.commit()

        mock_pr_url = "https://gitea.test/org/repo/pulls/1"
        patches = _approval_patches()
        with (
            patches["get_git_provider"] as mock_factory,
            patches["get_auth_url"],
            patches["get_ssh_for_run"],
            patches["RemoteGitOps"] as mock_remote_git_cls,
            patches["broadcaster"],
        ):
            mock_remote_git = mock_remote_git_cls.return_value
            # git log returns 1 commit ahead
            mock_remote_git.run_git = AsyncMock(return_value=_git_result("abc1234 some commit\n"))

            mock_provider = AsyncMock()
            mock_provider.create_pr.return_value = mock_pr_url
            mock_factory.return_value = mock_provider

            result = await approval.run(run, db_session, mock_services)

        assert result is None
        assert run.pr_url == mock_pr_url
        mock_remote_git.run_git.assert_called()
        mock_provider.create_pr.assert_called_once()

    async def test_uses_correct_git_provider(self, db_session, make_task_run, mock_services):
        run = make_task_run(git_provider="github")
        db_session.add(run)
        await db_session.commit()

        patches = _approval_patches()
        # Override auth URL for github
        patches["get_auth_url"] = patch(
            "backend.worker.phases.approval.get_auth_url",
            new=AsyncMock(return_value=("git@github.com:org/repo.git", "ssh")),
        )
        with (
            patches["get_git_provider"] as mock_factory,
            patches["get_auth_url"],
            patches["get_ssh_for_run"],
            patches["RemoteGitOps"] as mock_remote_git_cls,
            patches["broadcaster"],
        ):
            mock_remote_git = mock_remote_git_cls.return_value
            mock_remote_git.run_git = AsyncMock(return_value=_git_result("abc1234 some commit\n"))

            mock_provider = AsyncMock()
            mock_provider.create_pr.return_value = "https://github.com/pr/1"
            mock_factory.return_value = mock_provider

            await approval.run(run, db_session, mock_services)

        mock_factory.assert_called_once()
        call_args = mock_factory.call_args
        assert call_args[0][0] == "github"

    async def test_no_commits_raises(self, db_session, make_task_run, mock_services):
        """Approval fails early when no commits ahead of default branch."""
        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        patches = _approval_patches()
        with (
            patches["get_git_provider"],
            patches["get_auth_url"],
            patches["get_ssh_for_run"],
            patches["RemoteGitOps"] as mock_remote_git_cls,
            patches["broadcaster"],
        ):
            mock_remote_git = mock_remote_git_cls.return_value
            # git log returns empty (no commits ahead)
            mock_remote_git.run_git = AsyncMock(return_value=_git_result(""))

            import pytest

            with pytest.raises(RuntimeError, match="no commits ahead"):
                await approval.run(run, db_session, mock_services)
