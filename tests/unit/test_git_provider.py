# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for GitProvider protocol implementations and factory."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.services.git import (
    GiteaProvider,
    GitHubProvider,
    get_git_provider,
)


class TestGiteaProvider:
    def _make_provider(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return GiteaProvider(client, base_url="https://gitea.test", token="tok")

    async def test_create_repo_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=201)
        provider = self._make_provider(client)
        assert await provider.create_repo("org", "repo") is True
        client.post.assert_called_once()

    async def test_create_repo_already_exists(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=409)
        provider = self._make_provider(client)
        assert await provider.create_repo("org", "repo") is True

    async def test_create_repo_failure(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=500)
        provider = self._make_provider(client)
        assert await provider.create_repo("org", "repo") is False

    async def test_create_pr(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.json.return_value = {"html_url": "https://gitea.test/pr/1"}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        provider = self._make_provider(client)
        url = await provider.create_pr("org/repo", "title", "body", "feat", "main")
        assert url == "https://gitea.test/pr/1"

    async def test_create_pr_already_exists_returns_existing(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        # POST returns 409 (Gitea uses 409 for duplicate PR)
        post_resp = MagicMock(status_code=409)
        client.post.return_value = post_resp
        # GET returns existing PR
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = [
            {"head": {"ref": "feat"}, "html_url": "https://gitea.test/org/repo/pulls/42"},
        ]
        client.get.return_value = get_resp
        provider = self._make_provider(client)
        url = await provider.create_pr("org/repo", "title", "body", "feat", "main")
        assert url == "https://gitea.test/org/repo/pulls/42"

    async def test_merge_pr(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=200)
        provider = self._make_provider(client)
        assert await provider.merge_pr("https://gitea.test/org/repo/pulls/5") is True

    async def test_merge_pr_failure(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=409)
        provider = self._make_provider(client)
        assert await provider.merge_pr("https://gitea.test/org/repo/pulls/5") is False


class TestGiteaListIssues:
    def _make_provider(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return GiteaProvider(client, base_url="https://gitea.test", token="tok")

    async def test_list_issues_returns_normalized(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {
                "number": 1,
                "title": "Bug",
                "body": "Details",
                "labels": [{"name": "bug"}],
                "html_url": "https://gitea.test/org/repo/issues/1",
                "state": "open",
            },
        ]
        client.get.return_value = resp
        issues = await self._make_provider(client).list_issues("org/repo")
        assert len(issues) == 1
        assert issues[0]["number"] == 1
        assert issues[0]["labels"] == ["bug"]

    async def test_list_issues_empty(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = []
        client.get.return_value = resp
        assert await self._make_provider(client).list_issues("org/repo") == []

    async def test_list_issues_passes_type_param(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = []
        client.get.return_value = resp
        await self._make_provider(client).list_issues("org/repo")
        params = client.get.call_args[1]["params"]
        assert params["type"] == "issues"


class TestGitHubProvider:
    def _make_provider(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return GitHubProvider(client, base_url="https://api.github.com", token="ghp_tok")

    async def test_create_repo_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=201)
        provider = self._make_provider(client)
        assert await provider.create_repo("org", "repo") is True

    async def test_create_repo_already_exists(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=422)
        provider = self._make_provider(client)
        assert await provider.create_repo("org", "repo") is True

    async def test_create_pr(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.json.return_value = {"html_url": "https://github.com/org/repo/pull/1"}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        provider = self._make_provider(client)
        url = await provider.create_pr("org/repo", "title", "body", "feat", "main")
        assert url == "https://github.com/org/repo/pull/1"

    async def test_create_pr_already_exists_returns_existing(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        # POST returns 422 (GitHub uses 422 for duplicate PR)
        post_resp = MagicMock(status_code=422)
        client.post.return_value = post_resp
        # GET returns existing PR list
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = [
            {"head": {"ref": "feat"}, "html_url": "https://github.com/org/repo/pull/7"},
        ]
        client.get.return_value = get_resp
        provider = self._make_provider(client)
        url = await provider.create_pr("org/repo", "title", "body", "feat", "main")
        assert url == "https://github.com/org/repo/pull/7"

    async def test_create_pr_422_no_existing_pr_raises(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        # POST returns 422 but for a different reason (e.g., no commits)
        post_resp = MagicMock(status_code=422)
        post_resp.json.return_value = {"message": "No commits between main and feat"}
        client.post.return_value = post_resp
        # GET returns empty list (no matching PR)
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = []
        client.get.return_value = get_resp
        provider = self._make_provider(client)
        with pytest.raises(RuntimeError, match="GitHub PR creation failed"):
            await provider.create_pr("org/repo", "title", "body", "feat", "main")

    async def test_merge_pr_uses_put(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.put.return_value = MagicMock(status_code=200)
        provider = self._make_provider(client)
        assert await provider.merge_pr("https://github.com/org/repo/pull/3") is True
        client.put.assert_called_once()


class TestGitHubListIssues:
    def _make_provider(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return GitHubProvider(client, base_url="https://api.github.com", token="ghp_tok")

    async def test_list_issues_filters_prs(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {
                "number": 1,
                "title": "Issue",
                "body": "",
                "labels": [],
                "html_url": "",
                "state": "open",
            },
            {
                "number": 2,
                "title": "PR",
                "body": "",
                "labels": [],
                "html_url": "",
                "state": "open",
                "pull_request": {"url": "..."},
            },
        ]
        client.get.return_value = resp
        issues = await self._make_provider(client).list_issues("org/repo")
        assert len(issues) == 1
        assert issues[0]["number"] == 1

    async def test_list_issues_null_body(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {
                "number": 5,
                "title": "No body",
                "body": None,
                "labels": [],
                "html_url": "",
                "state": "open",
            },
        ]
        client.get.return_value = resp
        issues = await self._make_provider(client).list_issues("org/repo")
        assert issues[0]["body"] == ""


class TestFactory:
    def test_returns_github_provider(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("github", client)
        assert isinstance(p, GitHubProvider)

    def test_returns_gitea_provider_default(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("gitea", client)
        assert isinstance(p, GiteaProvider)

    def test_returns_gitea_for_unknown(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("unknown", client)
        assert isinstance(p, GiteaProvider)
