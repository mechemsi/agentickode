# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for finalization phase."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.worker.phases import finalization


class TestFinalization:
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
