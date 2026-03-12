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