# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for reviewing phase."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.git import GitResult
from backend.services.role_resolver import ResolvedRole
from backend.worker.phases import reviewing


def _patch_reviewing():
    """Common patches for reviewing tests."""
    mock_broadcaster = MagicMock(log=AsyncMock(), event=AsyncMock())
    return (
        patch(
            "backend.worker.phases.reviewing.broadcaster",
            new=mock_broadcaster,
        ),
        patch(
            "backend.worker.phases._reviewing_loop.broadcaster",
            new=mock_broadcaster,
        ),
        patch(
            "backend.worker.phases.reviewing.get_workspace_server_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "backend.worker.phases.reviewing.get_ssh_for_run",
            new=AsyncMock(return_value=AsyncMock()),
        ),
        patch(
            "backend.worker.phases.reviewing.RemoteGitOps",
        ),
    )


class TestReviewing:
    async def test_review_passes(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            coding_results={"results": [{"files_changed": ["a.py"]}]},
        )
        db_session.add(run)
        await db_session.commit()

        reviewer_adapter = AsyncMock()
        reviewer_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        reviewer_adapter.generate.return_value = (
            '{"approved": true, "issues": [], "suggestions": []}'
        )
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=reviewer_adapter)

        p1, p2, p3, p4, p5 = _patch_reviewing()
        with p1, p2, p3, p4, p5 as mock_git_cls:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.run_git = AsyncMock(
                return_value=GitResult(stdout="+added line", stderr="")
            )
            await reviewing.run(run, db_session, mock_services)

        assert run.review_result["approved"] is True

    async def test_critical_issues_trigger_retry(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            coding_results={"results": [{"files_changed": ["a.py"]}]},
            max_retries=1,
        )
        db_session.add(run)
        await db_session.commit()

        # Reviewer adapter
        reviewer_adapter = AsyncMock()
        reviewer_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        reviewer_adapter.generate.side_effect = [
            '{"approved": false, "issues": [{"severity": "critical", "description": "bug"}], "suggestions": []}',
            '{"approved": true, "issues": [], "suggestions": []}',
        ]

        # Coder adapter (for fix)
        coder_adapter = AsyncMock()
        coder_adapter.provider_name = "agent/openhands"
        coder_adapter.run_task.return_value = {"files_changed": []}

        # First call returns reviewer, second returns coder (for fix)
        mock_services.role_resolver.resolve.side_effect = [
            ResolvedRole(adapter=reviewer_adapter),
            ResolvedRole(adapter=coder_adapter),
        ]

        p1, p2, p3, p4, p5 = _patch_reviewing()
        with p1, p2, p3, p4, p5 as mock_git_cls:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.run_git = AsyncMock(return_value=GitResult(stdout="+line", stderr=""))
            await reviewing.run(run, db_session, mock_services)

        assert run.review_result["approved"] is True
        assert run.retry_count == 1

    async def test_parse_failure_sets_not_approved(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            coding_results={"results": [{"files_changed": ["a.py"]}]},
        )
        db_session.add(run)
        await db_session.commit()

        reviewer_adapter = AsyncMock()
        reviewer_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        reviewer_adapter.generate.return_value = "garbage not json"
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=reviewer_adapter)

        p1, p2, p3, p4, p5 = _patch_reviewing()
        with p1, p2, p3, p4, p5 as mock_git_cls:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.run_git = AsyncMock(return_value=GitResult(stdout="+line", stderr=""))
            await reviewing.run(run, db_session, mock_services)

        assert run.review_result["approved"] is False

    async def test_critical_override_prevents_approval(
        self, db_session, make_task_run, mock_services
    ):
        run = make_task_run(
            coding_results={"results": [{"files_changed": ["a.py"]}]},
            max_retries=0,
        )
        db_session.add(run)
        await db_session.commit()

        reviewer_adapter = AsyncMock()
        reviewer_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        reviewer_adapter.generate.return_value = '{"approved": true, "issues": [{"severity": "critical", "description": "security hole"}], "suggestions": []}'
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=reviewer_adapter)

        p1, p2, p3, p4, p5 = _patch_reviewing()
        with p1, p2, p3, p4, p5 as mock_git_cls:
            mock_remote_git = mock_git_cls.return_value
            mock_remote_git.run_git = AsyncMock(return_value=GitResult(stdout="+line", stderr=""))
            await reviewing.run(run, db_session, mock_services)

        assert run.review_result["approved"] is False
