# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for NotionPagePoller."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models import ProjectConfig, TaskRun
from backend.services.task_source_polling.notion_poller import NotionPagePoller


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
        poll_enabled=True,
        integration_config={
            "notion_api_key": "secret",
            "notion_database_id": "db-xyz",
        },
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


def _page(page_id, title="", tags=("ai-task",), status=""):
    props = {
        "Name": {"type": "title", "title": [{"plain_text": title}]},
        "Tags": {"multi_select": [{"name": t} for t in tags]},
        "Status": {"select": {"name": status}} if status else {"select": None},
    }
    return {"id": page_id, "url": f"https://notion.so/{page_id}", "properties": props}


def _patch_client(pages):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = lambda: {"results": pages}

    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    return patch(
        "backend.services.task_source_polling.notion_poller.get_http_client",
        return_value=client,
    ), client


class TestNotionPagePoller:
    async def test_creates_runs_for_new_ai_task_pages(self, db_session, notion_project):
        pages = [
            _page("p1", "First", tags=("ai-task",)),
            _page("p2", "Claude one", tags=("ai-task", "use-claude")),
            _page("p3", "Done already", tags=("ai-task",), status="Done"),
        ]
        ctx, client = _patch_client(pages)
        with ctx:
            created = await NotionPagePoller().poll(notion_project, db_session)
        await db_session.commit()

        # Notion query payload uses the database id and filters on Tags
        payload = client.post.call_args.kwargs["json"]
        assert payload["filter"]["property"] == "Tags"
        assert payload["filter"]["multi_select"]["contains"] == "ai-task"

        from sqlalchemy import select

        runs = (await db_session.execute(select(TaskRun))).scalars().all()
        assert len(created) == 2
        assert {r.task_id for r in runs} == {"p1", "p2"}
        claude_run = next(r for r in runs if r.task_id == "p2")
        assert claude_run.use_claude_api is True
        assert claude_run.task_source == "notion"
        assert claude_run.task_source_meta["database_id"] == "db-xyz"

    async def test_no_runs_without_api_key(self, db_session, notion_project):
        notion_project.integration_config = {"notion_database_id": "db-xyz"}
        await db_session.commit()
        ctx, _client = _patch_client([_page("p9", "x")])
        with ctx:
            created = await NotionPagePoller().poll(notion_project, db_session)
        assert created == []
