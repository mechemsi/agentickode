# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for POST /webhooks/gitlab (GitLab issue events)."""

import pytest
from httpx import AsyncClient

from backend.models import ProjectConfig


@pytest.fixture()
async def gitlab_project(db_session):
    """Create a test project configured for GitLab."""
    p = ProjectConfig(
        project_id="gitlab-proj",
        project_slug="gitlab-proj",
        repo_owner="mygroup",
        repo_name="myrepo",
        default_branch="main",
        task_source="gitlab",
        git_provider="gitlab",
        workspace_path="/workspaces/myrepo",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


def _make_payload(
    object_kind="issue",
    action="open",
    labels=None,
    issue_iid=42,
    title="Fix login bug",
    description="Description here",
    issue_url="https://gitlab.com/mygroup/myrepo/-/issues/42",
    path_with_namespace="mygroup/myrepo",
):
    if labels is None:
        labels = [{"title": "ai-task"}]
    return {
        "object_kind": object_kind,
        "event_type": "issue",
        "object_attributes": {
            "iid": issue_iid,
            "action": action,
            "title": title,
            "description": description,
            "url": issue_url,
        },
        "labels": labels,
        "project": {
            "path_with_namespace": path_with_namespace,
        },
    }


class TestGitLabIssueWebhook:
    async def test_non_issue_object_kind_is_ignored(self, client: AsyncClient, gitlab_project):
        payload = _make_payload(object_kind="push")
        resp = await client.post("/api/webhooks/gitlab", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert "object_kind_push" in data["reason"]

    async def test_non_open_update_action_is_ignored(self, client: AsyncClient, gitlab_project):
        payload = _make_payload(action="close")
        resp = await client.post("/api/webhooks/gitlab", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "action_close"

    async def test_no_ai_task_label_is_ignored(self, client: AsyncClient, gitlab_project):
        payload = _make_payload(labels=[{"title": "backend"}, {"title": "bug"}])
        resp = await client.post("/api/webhooks/gitlab", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "not_ai_task"

    async def test_labels_use_title_key_not_name(self, client: AsyncClient, gitlab_project):
        # Labels with "name" key (GitHub style) should NOT trigger
        payload = _make_payload(labels=[{"name": "ai-task"}])
        resp = await client.post("/api/webhooks/gitlab", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "not_ai_task"

    async def test_unknown_project_is_ignored(self, client: AsyncClient, gitlab_project):
        payload = _make_payload(path_with_namespace="unknown/norepo")
        resp = await client.post("/api/webhooks/gitlab", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "unknown_project"

    async def test_valid_open_webhook_creates_task_run(
        self, client: AsyncClient, gitlab_project, db_session
    ):
        payload = _make_payload(
            action="open",
            labels=[{"title": "ai-task"}, {"title": "backend"}],
            issue_iid=42,
            title="Fix login bug",
            description="Description here",
            issue_url="https://gitlab.com/mygroup/myrepo/-/issues/42",
        )
        resp = await client.post("/api/webhooks/gitlab", json=payload)
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
        assert run.task_source == "gitlab"
        assert run.task_source_meta["issue_iid"] == 42
        assert run.task_source_meta["issue_url"] == "https://gitlab.com/mygroup/myrepo/-/issues/42"
        assert run.task_source_meta["repo_full_name"] == "mygroup/myrepo"
        assert "ai-task" in run.task_source_meta["labels"]

    async def test_update_action_also_triggers(self, client: AsyncClient, gitlab_project):
        payload = _make_payload(action="update")
        resp = await client.post("/api/webhooks/gitlab", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_use_claude_label_sets_flag(
        self, client: AsyncClient, gitlab_project, db_session
    ):
        payload = _make_payload(
            labels=[{"title": "ai-task"}, {"title": "use-claude"}],
        )
        resp = await client.post("/api/webhooks/gitlab", json=payload)
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.use_claude_api is True

    async def test_without_use_claude_label_flag_is_false(
        self, client: AsyncClient, gitlab_project, db_session
    ):
        payload = _make_payload(labels=[{"title": "ai-task"}])
        resp = await client.post("/api/webhooks/gitlab", json=payload)
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.use_claude_api is False
