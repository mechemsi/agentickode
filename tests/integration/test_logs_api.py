# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for the Logs API endpoints."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models import TaskLog, TaskRun


@pytest.fixture()
async def seeded_run_with_logs(db_engine):
    """Create a project, run, and logs for testing phase filtering."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        from backend.models import ProjectConfig

        project = ProjectConfig(
            project_id="proj-logs",
            project_slug="logs-project",
            repo_owner="org",
            repo_name="repo",
        )
        session.add(project)
        await session.flush()

        run = TaskRun(
            task_id="TASK-LOG-1",
            project_id="proj-logs",
            title="Log test",
            description="",
            branch_name="feature/ai-TASK-LOG-1",
            workspace_path="/workspaces/proj-logs",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="plane",
            git_provider="gitea",
            task_source_meta={},
            status="running",
            max_retries=3,
        )
        session.add(run)
        await session.flush()

        logs = [
            TaskLog(run_id=run.id, level="info", phase="planning", message="Planning started"),
            TaskLog(run_id=run.id, level="info", phase="planning", message="Planning done"),
            TaskLog(run_id=run.id, level="info", phase="coding", message="Coding started"),
            TaskLog(run_id=run.id, level="error", phase="coding", message="Coding error"),
            TaskLog(
                run_id=run.id,
                level="info",
                phase="reviewing",
                message="Review started",
                metadata_={"category": "system_prompt", "system_prompt_text": "You are a reviewer"},
            ),
        ]
        session.add_all(logs)
        await session.commit()
        return run.id


class TestLogsApi:
    async def test_get_all_logs(self, client, seeded_run_with_logs):
        run_id = seeded_run_with_logs
        resp = await client.get(f"/api/runs/{run_id}/logs")
        assert resp.status_code == 200
        assert len(resp.json()) == 5

    async def test_filter_by_phase(self, client, seeded_run_with_logs):
        run_id = seeded_run_with_logs
        resp = await client.get(f"/api/runs/{run_id}/logs?phase=planning")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(log["phase"] == "planning" for log in data)

    async def test_filter_nonexistent_phase_returns_empty(self, client, seeded_run_with_logs):
        run_id = seeded_run_with_logs
        resp = await client.get(f"/api/runs/{run_id}/logs?phase=nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_filter_phase_and_level_combined(self, client, seeded_run_with_logs):
        run_id = seeded_run_with_logs
        resp = await client.get(f"/api/runs/{run_id}/logs?phase=coding&level=error")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["phase"] == "coding"
        assert data[0]["level"] == "error"
        assert data[0]["message"] == "Coding error"

    async def test_metadata_returned_in_response(self, client, seeded_run_with_logs):
        run_id = seeded_run_with_logs
        resp = await client.get(f"/api/runs/{run_id}/logs?phase=reviewing")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["metadata_"]["category"] == "system_prompt"
        assert "system_prompt_text" in data[0]["metadata_"]

    async def test_metadata_null_when_absent(self, client, seeded_run_with_logs):
        run_id = seeded_run_with_logs
        resp = await client.get(f"/api/runs/{run_id}/logs?phase=planning")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["metadata_"] is None