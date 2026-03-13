# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for POST /webhooks/gitea (Gitea issue events)."""

import pytest
from httpx import AsyncClient

from backend.models import ProjectConfig


@pytest.fixture()
async def gitea_project(db_session):
    """Create a test project configured for Gitea."""
    p = ProjectConfig(
        project_id="gitea-proj",
        project_slug="gitea-proj",
        repo_owner="myorg",
        repo_name="myrepo",
        default_branch="main",
        task_source="gitea",
        git_provider="gitea",
        workspace_path="/workspaces/myrepo",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


def _make_payload(
    action="opened",
    labels=None,
    issue_number=42,
    title="Fix login bug",
    body="Description here",
    repo_full_name="myorg/myrepo",
):
    if labels is None:
        labels = [{"name": "ai-task"}]
    return {
        "action": action,
        "issue": {
            "number": issue_number,
            "title": title,
            "body": body,
            "labels": labels,
        },
        "repository": {
            "full_name": repo_full_name,
        },
    }


class TestGiteaIssueWebhook:
    async def test_non_opened_labeled_action_is_ignored(self, client: AsyncClient, gitea_project):
        payload = _make_payload(action="closed")
        resp = await client.post("/api/webhooks/gitea", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "action_closed"

    async def test_no_ai_task_label_is_ignored(self, client: AsyncClient, gitea_project):
        payload = _make_payload(labels=[{"name": "backend"}, {"name": "bug"}])
        resp = await client.post("/api/webhooks/gitea", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "not_ai_task"

    async def test_unknown_project_is_ignored(self, client: AsyncClient, gitea_project):
        payload = _make_payload(repo_full_name="unknown/norepo")
        resp = await client.post("/api/webhooks/gitea", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "unknown_project"

    async def test_valid_webhook_creates_task_run(
        self, client: AsyncClient, gitea_project, db_session
    ):
        payload = _make_payload(
            action="opened",
            labels=[{"name": "ai-task"}, {"name": "backend"}],
            issue_number=42,
            title="Fix login bug",
            body="Description here",
        )
        resp = await client.post("/api/webhooks/gitea", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["run_id"] > 0

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, data["run_id"])
        assert run is not None
        assert run.task_id == "42"
        assert run.title == "Fix login bug"
        assert run.description == "Description here"
        assert run.task_source == "gitea"
        assert run.task_source_meta["issue_number"] == 42
        assert run.task_source_meta["repo_full_name"] == "myorg/myrepo"
        assert "ai-task" in run.task_source_meta["labels"]

    async def test_labeled_action_also_triggers(self, client: AsyncClient, gitea_project):
        payload = _make_payload(action="labeled")
        resp = await client.post("/api/webhooks/gitea", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_use_claude_label_sets_flag(self, client: AsyncClient, gitea_project, db_session):
        payload = _make_payload(
            labels=[{"name": "ai-task"}, {"name": "use-claude"}],
        )
        resp = await client.post("/api/webhooks/gitea", json=payload)
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.use_claude_api is True

    async def test_without_use_claude_label_flag_is_false(
        self, client: AsyncClient, gitea_project, db_session
    ):
        payload = _make_payload(labels=[{"name": "ai-task"}])
        resp = await client.post("/api/webhooks/gitea", json=payload)
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.use_claude_api is False
