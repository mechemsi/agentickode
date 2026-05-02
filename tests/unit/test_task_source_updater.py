# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for TaskSourceUpdater service."""

from unittest.mock import AsyncMock

import httpx
import pytest

from backend.services.task_source_updater import TaskSourceUpdater


@pytest.fixture()
def mock_client():
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture()
def updater(mock_client):
    return TaskSourceUpdater(mock_client)


class TestTaskSourceUpdater:
    async def test_notify_github_posts_comment(self, updater, mock_client):
        mock_client.post.return_value = httpx.Response(201)
        meta = {
            "comments_url": "https://api.github.com/repos/o/r/issues/1/comments",
            "github_token": "tok",
        }

        await updater.notify(
            "github", meta, "coding", "completed", run_id=1, pr_url="https://pr.url"
        )

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == meta["comments_url"]
        body = call_args[1]["json"]["body"]
        assert "Run #1" in body
        assert "coding" in body
        assert "https://pr.url" in body
        assert call_args[1]["headers"]["Authorization"] == "token tok"

    async def test_notify_github_without_comments_url_skips(self, updater, mock_client):
        await updater.notify("github", {}, "coding", "completed", run_id=1)
        mock_client.post.assert_not_called()

    async def test_notify_plane_posts_comment(self, updater, mock_client):
        mock_client.post.return_value = httpx.Response(201)
        meta = {
            "plane_api_url": "https://plane.example.com",
            "plane_api_key": "key123",
            "issue_id": "issue-1",
            "workspace_slug": "ws",
            "project_id": "proj-1",
        }

        await updater.notify("plane", meta, "reviewing", "completed", run_id=2)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/comments/" in call_args[0][0]
        assert call_args[1]["headers"]["X-API-Key"] == "key123"

    async def test_notify_plane_incomplete_meta_skips(self, updater, mock_client):
        await updater.notify(
            "plane", {"plane_api_url": "https://plane.example.com"}, "coding", "completed", run_id=1
        )
        mock_client.post.assert_not_called()

    async def test_notify_unknown_source_skips(self, updater, mock_client):
        await updater.notify("jira", {}, "coding", "completed", run_id=1)
        mock_client.post.assert_not_called()

    async def test_notify_handles_exception_gracefully(self, updater, mock_client):
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        meta = {"comments_url": "https://api.github.com/repos/o/r/issues/1/comments"}

        # Should not raise
        await updater.notify("github", meta, "coding", "completed", run_id=1)

    async def test_notify_notion_with_plaintext_key(self, updater, mock_client):
        mock_client.post.return_value = httpx.Response(200)
        meta = {"page_id": "page-abc"}
        cfg = {"notion_api_key": "plain-secret"}

        await updater.notify(
            "notion",
            meta,
            "reviewing",
            "completed",
            run_id=42,
            pr_url="https://pr.url",
            project_integration_config=cfg,
        )

        mock_client.post.assert_called_once()
        url = mock_client.post.call_args.args[0]
        headers = mock_client.post.call_args.kwargs["headers"]
        payload = mock_client.post.call_args.kwargs["json"]
        assert url == "https://api.notion.com/v1/comments"
        assert headers["Authorization"] == "Bearer plain-secret"
        assert headers["Notion-Version"] == "2022-06-28"
        assert payload["parent"]["page_id"] == "page-abc"
        body = payload["rich_text"][0]["text"]["content"]
        assert "Run #42" in body
        assert "reviewing" in body
        assert "https://pr.url" in body

    async def test_notify_notion_with_encrypted_key(self, updater, mock_client):
        from backend.services.encryption import encrypt_value

        mock_client.post.return_value = httpx.Response(200)
        cfg = {"notion_api_key_enc": encrypt_value("real-secret")}
        meta = {"page_id": "page-xyz"}

        await updater.notify(
            "notion",
            meta,
            "coding",
            "completed",
            run_id=7,
            project_integration_config=cfg,
        )

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer real-secret"

    async def test_notify_notion_without_page_id_skips(self, updater, mock_client):
        await updater.notify(
            "notion",
            {},
            "coding",
            "completed",
            run_id=1,
            project_integration_config={"notion_api_key": "x"},
        )
        mock_client.post.assert_not_called()

    async def test_notify_notion_without_api_key_skips(self, updater, mock_client):
        await updater.notify(
            "notion",
            {"page_id": "abc"},
            "coding",
            "completed",
            run_id=1,
            project_integration_config={},
        )
        mock_client.post.assert_not_called()
