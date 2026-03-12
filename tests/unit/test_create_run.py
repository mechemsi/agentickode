# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for POST /runs endpoint."""

import pytest
from httpx import AsyncClient

from backend.models import ProjectConfig


@pytest.fixture()
async def project(db_session):
    """Create a test project in the DB."""
    p = ProjectConfig(
        project_id="test-proj",
        project_slug="test-proj",
        repo_owner="org",
        repo_name="myrepo",
        default_branch="main",
        task_source="manual",
        git_provider="gitea",
        workspace_path="/workspaces/myrepo",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


class TestCreateRun:
    async def test_create_run_success(self, client: AsyncClient, project):
        resp = await client.post(
            "/api/runs",
            json={
                "project_id": "test-proj",
                "title": "Fix the login bug",
                "description": "Detailed description",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["title"] == "Fix the login bug"
        assert data["project_id"] == "test-proj"
        assert data["id"] > 0
        assert "autodev/test-proj/" in data["branch_name"]

    async def test_create_run_missing_project_returns_404(self, client: AsyncClient):
        resp = await client.post(
            "/api/runs",
            json={
                "project_id": "nonexistent",
                "title": "Should fail",
            },
        )
        assert resp.status_code == 404

    async def test_create_run_with_workflow_template_id(self, client: AsyncClient, project):
        resp = await client.post(
            "/api/runs",
            json={
                "project_id": "test-proj",
                "title": "Templated run",
                "workflow_template_id": 42,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Templated run"

    async def test_create_run_with_agent_override_stored_in_meta(
        self, client: AsyncClient, project, db_session
    ):
        resp = await client.post(
            "/api/runs",
            json={
                "project_id": "test-proj",
                "title": "Agent override run",
                "agent_override": "claude",
            },
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.task_source_meta["agent_override"] == "claude"

    async def test_create_run_with_phase_overrides_stored_in_meta(
        self, client: AsyncClient, project, db_session
    ):
        phase_overrides = {
            "coding": {"agent_override": "claude"},
            "reviewing": {"agent_override": "codex"},
        }
        resp = await client.post(
            "/api/runs",
            json={
                "project_id": "test-proj",
                "title": "Phase override run",
                "phase_overrides": phase_overrides,
            },
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.task_source_meta["phase_overrides"] == phase_overrides

    async def test_create_run_branch_name_format(self, client: AsyncClient, project):
        resp = await client.post(
            "/api/runs",
            json={
                "project_id": "test-proj",
                "title": "Branch name test",
            },
        )
        assert resp.status_code == 201
        branch = resp.json()["branch_name"]
        # Format: autodev/{slug}/{timestamp}
        parts = branch.split("/")
        assert parts[0] == "autodev"
        assert parts[1] == "test-proj"
        assert parts[2].isdigit()

    async def test_create_run_task_source_is_manual(self, client: AsyncClient, project, db_session):
        resp = await client.post(
            "/api/runs",
            json={
                "project_id": "test-proj",
                "title": "Manual task source",
            },
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.task_source == "manual"

    async def test_create_run_with_labels(self, client: AsyncClient, project, db_session):
        resp = await client.post(
            "/api/runs",
            json={
                "project_id": "test-proj",
                "title": "Labelled run",
                "labels": ["bug", "frontend"],
            },
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.task_source_meta["labels"] == ["bug", "frontend"]