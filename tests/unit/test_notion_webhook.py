# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for POST /webhooks/notion."""

import pytest
from httpx import AsyncClient

from backend.models import ProjectConfig


@pytest.fixture()
async def notion_project(db_session):
    p = ProjectConfig(
        project_id="notion-proj",
        project_slug="notion-proj",
        repo_owner="",
        repo_name="",
        default_branch="main",
        task_source="notion",
        git_provider="gitea",
        workspace_path="/workspaces/notion",
        integration_config={"notion_database_id": "db-xyz"},
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


def _make_page(
    page_id="page-1",
    tags=("ai-task",),
    title="Ship it",
    status="To Do",
    database_id="db-xyz",
):
    return {
        "event": "page.created",
        "page": {
            "id": page_id,
            "url": f"https://notion.so/{page_id}",
            "parent": {"database_id": database_id},
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": title}]},
                "Tags": {"multi_select": [{"name": t} for t in tags]},
                "Status": {"select": {"name": status}},
            },
        },
    }


class TestNotionWebhook:
    async def test_verification_handshake(self, client: AsyncClient):
        resp = await client.post(
            "/api/webhooks/notion", json={"verification_token": "notion-tok-123"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"verification_token": "notion-tok-123"}

    async def test_no_ai_task_tag_is_ignored(self, client: AsyncClient, notion_project):
        resp = await client.post("/api/webhooks/notion", json=_make_page(tags=("not-ai",)))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    async def test_unknown_database_is_ignored(self, client: AsyncClient, notion_project):
        resp = await client.post("/api/webhooks/notion", json=_make_page(database_id="other-db"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    async def test_ai_task_page_creates_run(self, client: AsyncClient, notion_project, db_session):
        resp = await client.post("/api/webhooks/notion", json=_make_page())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["run_id"] > 0

        from backend.models import TaskRun

        run = await db_session.get(TaskRun, body["run_id"])
        assert run is not None
        assert run.task_source == "notion"
        assert run.task_id == "page-1"
        assert run.task_source_meta["database_id"] == "db-xyz"
        assert run.task_source_meta["tags"] == ["ai-task"]

    async def test_use_claude_tag_sets_flag(self, client: AsyncClient, notion_project, db_session):
        resp = await client.post(
            "/api/webhooks/notion", json=_make_page(tags=("ai-task", "use-claude"))
        )
        run_id = resp.json()["run_id"]
        from backend.models import TaskRun

        run = await db_session.get(TaskRun, run_id)
        assert run is not None
        assert run.use_claude_api is True

    async def test_duplicate_page_is_ignored(self, client: AsyncClient, notion_project):
        first = await client.post("/api/webhooks/notion", json=_make_page())
        assert first.json()["status"] == "accepted"
        second = await client.post("/api/webhooks/notion", json=_make_page())
        assert second.json()["status"] == "ignored"
        assert second.json()["reason"] == "duplicate"
