# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for A/B comparison mode (F12)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models import ProjectConfig
from backend.services.role_resolver import ResolvedRole
from backend.worker.phases import coding


class TestComparisonDetection:
    """coding.run detects comparison config and delegates."""

    async def test_delegates_to_comparison(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            planning_result={
                "subtasks": [{"title": "T", "description": "D", "files_likely_affected": []}]
            }
        )
        db_session.add(run)
        await db_session.commit()

        phase_config = {"params": {"comparison": {"agents": ["claude", "codex"]}}}

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=1),
            ),
            patch(
                "backend.worker.phases._comparison.run_comparison",
                new=AsyncMock(),
            ) as mock_comp,
        ):
            await coding.run(run, db_session, mock_services, phase_config=phase_config)

        mock_comp.assert_called_once()
        # role_resolver should NOT have been called (early return before normal flow)
        mock_services.role_resolver.resolve.assert_not_called()

    async def test_no_comparison_runs_normally(self, db_session, make_task_run, mock_services):
        """Without comparison config, coding runs the normal path."""
        run = make_task_run(
            planning_result={
                "subtasks": [{"title": "T", "description": "D", "files_likely_affected": []}]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws"
        mock_adapter.run_task.return_value = {
            "files_changed": ["f.py"],
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
        ):
            await coding.run(run, db_session, mock_services)

        # Normal flow was executed
        mock_services.role_resolver.resolve.assert_called_once()


class TestComparisonResults:
    """run_comparison stores the expected structure."""

    async def test_stores_comparison_results(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            planning_result={
                "subtasks": [{"title": "T", "description": "D", "files_likely_affected": []}]
            }
        )
        db_session.add(run)

        # Need a project config for get_ssh_for_run
        proj = ProjectConfig(
            project_id=run.project_id,
            project_slug="proj",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="manual",
            git_provider="gitea",
            workspace_server_id=None,
        )
        db_session.add(proj)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws"
        mock_adapter.run_task.return_value = {
            "files_changed": ["a.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        mock_git = MagicMock()
        mock_git.run_git = AsyncMock(return_value=MagicMock(stdout="abc123\n", stderr=""))
        mock_ssh = MagicMock()

        phase_config = {"params": {"comparison": {"agents": ["claude", "codex"]}}}

        with (
            patch(
                "backend.worker.phases._comparison.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases._comparison.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch(
                "backend.worker.phases._comparison.RemoteGitOps",
                return_value=mock_git,
            ),
            patch(
                "backend.worker.phases._comparison.ensure_agent_ready",
                new=AsyncMock(),
            ),
        ):
            from backend.worker.phases._comparison import run_comparison

            await run_comparison(
                run,
                db_session,
                mock_services,
                phase_config,
                [{"title": "T", "description": "D", "files_likely_affected": []}],
                None,
                None,
            )

        results = run.coding_results
        assert results["comparison_mode"] is True
        assert results["base_commit"] == "abc123"
        assert "a" in results["agents"]
        assert "b" in results["agents"]
        assert results["agents"]["a"]["agent_name"] == "claude"
        assert results["agents"]["b"]["agent_name"] == "codex"
        assert results["winner"] is None
        assert len(results["agents"]["a"]["results"]) == 1
        assert len(results["agents"]["b"]["results"]) == 1

    async def test_comparison_requires_two_agents(self, db_session, make_task_run, mock_services):
        run = make_task_run()
        db_session.add(run)

        proj = ProjectConfig(
            project_id=run.project_id,
            project_slug="proj",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="manual",
            git_provider="gitea",
            workspace_server_id=None,
        )
        db_session.add(proj)
        await db_session.commit()

        mock_ssh = MagicMock()
        mock_git = MagicMock()
        mock_git.run_git = AsyncMock(return_value=MagicMock(stdout="abc123\n", stderr=""))

        phase_config = {"params": {"comparison": {"agents": ["claude"]}}}

        with (
            patch(
                "backend.worker.phases._comparison.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases._comparison.get_ssh_for_run",
                new=AsyncMock(return_value=mock_ssh),
            ),
            patch(
                "backend.worker.phases._comparison.RemoteGitOps",
                return_value=mock_git,
            ),
            pytest.raises(ValueError, match="at least 2"),
        ):
            from backend.worker.phases._comparison import run_comparison

            await run_comparison(
                run,
                db_session,
                mock_services,
                phase_config,
                [],
                None,
                None,
            )


class TestPickWinnerEndpoint:
    """API endpoint for picking comparison winner."""

    async def test_pick_winner_success(self, client, db_session):
        from backend.models import TaskRun

        run = TaskRun(
            task_id="TASK-1",
            project_id="proj-1",
            title="Test",
            description="",
            branch_name="agentickode/test/1",
            workspace_path="/ws",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="manual",
            git_provider="gitea",
            task_source_meta={},
            status="completed",
            coding_results={
                "comparison_mode": True,
                "base_commit": "abc123",
                "agents": {
                    "a": {"agent_name": "claude", "branch": "compare-claude-1", "results": []},
                    "b": {"agent_name": "codex", "branch": "compare-codex-1", "results": []},
                },
                "winner": None,
            },
        )
        db_session.add(run)
        await db_session.commit()

        resp = await client.post(
            f"/api/runs/{run.id}/comparison/pick-winner",
            json={"winner": "a"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "winner_picked"
        assert data["winner"] == "a"
        assert data["agent_name"] == "claude"

    async def test_pick_winner_not_comparison(self, client, db_session):
        from backend.models import TaskRun

        run = TaskRun(
            task_id="TASK-2",
            project_id="proj-1",
            title="Normal run",
            description="",
            branch_name="agentickode/test/2",
            workspace_path="/ws",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="manual",
            git_provider="gitea",
            task_source_meta={},
            status="completed",
            coding_results={"results": []},
        )
        db_session.add(run)
        await db_session.commit()

        resp = await client.post(
            f"/api/runs/{run.id}/comparison/pick-winner",
            json={"winner": "a"},
        )
        assert resp.status_code == 400

    async def test_pick_winner_invalid_choice(self, client, db_session):
        from backend.models import TaskRun

        run = TaskRun(
            task_id="TASK-3",
            project_id="proj-1",
            title="Test",
            description="",
            branch_name="agentickode/test/3",
            workspace_path="/ws",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="manual",
            git_provider="gitea",
            task_source_meta={},
            status="completed",
            coding_results={
                "comparison_mode": True,
                "base_commit": "abc",
                "agents": {
                    "a": {"agent_name": "claude", "branch": "b1", "results": []},
                    "b": {"agent_name": "codex", "branch": "b2", "results": []},
                },
                "winner": None,
            },
        )
        db_session.add(run)
        await db_session.commit()

        resp = await client.post(
            f"/api/runs/{run.id}/comparison/pick-winner",
            json={"winner": "c"},
        )
        assert resp.status_code == 400

    async def test_pick_winner_idempotent(self, client, db_session):
        from backend.models import TaskRun

        run = TaskRun(
            task_id="TASK-4",
            project_id="proj-1",
            title="Test",
            description="",
            branch_name="agentickode/test/4",
            workspace_path="/ws",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="manual",
            git_provider="gitea",
            task_source_meta={},
            status="completed",
            coding_results={
                "comparison_mode": True,
                "base_commit": "abc",
                "agents": {
                    "a": {"agent_name": "claude", "branch": "b1", "results": []},
                    "b": {"agent_name": "codex", "branch": "b2", "results": []},
                },
                "winner": "a",
            },
        )
        db_session.add(run)
        await db_session.commit()

        # Re-picking should still succeed
        resp = await client.post(
            f"/api/runs/{run.id}/comparison/pick-winner",
            json={"winner": "b"},
        )
        assert resp.status_code == 200
        assert resp.json()["winner"] == "b"
