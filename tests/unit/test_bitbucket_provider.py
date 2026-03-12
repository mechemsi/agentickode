# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for BitbucketProvider — Bitbucket Cloud REST API v2.0 implementation."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.services.git import BitbucketProvider, get_git_provider


class TestBitbucketProvider:
    def _make_provider(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return BitbucketProvider(
            client,
            base_url="https://api.bitbucket.org",
            access_token="secret",
        )

    # --- create_repo ---

    async def test_create_repo_success_201(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=201)
        provider = self._make_provider(client)
        assert await provider.create_repo("myworkspace", "myrepo") is True
        client.post.assert_called_once()
        call_kwargs = client.post.call_args
        assert "myworkspace/myrepo" in call_kwargs[0][0]
        assert call_kwargs[1]["json"] == {"scm": "git", "is_private": True}

    async def test_create_repo_success_200(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=200)
        provider = self._make_provider(client)
        assert await provider.create_repo("myworkspace", "myrepo") is True

    async def test_create_repo_already_exists_409(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=409)
        provider = self._make_provider(client)
        assert await provider.create_repo("myworkspace", "myrepo") is True

    async def test_create_repo_failure_500(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=500)
        provider = self._make_provider(client)
        assert await provider.create_repo("myworkspace", "myrepo") is False

    # --- create_pr ---

    async def test_create_pr_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 201
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "links": {"html": {"href": "https://bitbucket.org/ws/repo/pull-requests/7"}}
        }
        client.post.return_value = resp
        provider = self._make_provider(client)

        url = await provider.create_pr("ws/repo", "My PR", "Description", "feature", "main")

        assert url == "https://bitbucket.org/ws/repo/pull-requests/7"
        call_args = client.post.call_args
        assert "ws/repo/pullrequests" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["title"] == "My PR"
        assert payload["description"] == "Description"
        assert payload["source"]["branch"]["name"] == "feature"
        assert payload["destination"]["branch"]["name"] == "main"

    async def test_create_pr_returns_links_html_href(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "id": 1,
            "links": {"html": {"href": "https://bitbucket.org/org/proj/pull-requests/42"}},
        }
        client.post.return_value = resp
        provider = self._make_provider(client)

        result = await provider.create_pr("org/proj", "title", "body", "feat", "develop")
        assert result == "https://bitbucket.org/org/proj/pull-requests/42"

    async def test_create_pr_raises_on_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400", request=MagicMock(), response=resp
        )
        client.post.return_value = resp
        provider = self._make_provider(client)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.create_pr("ws/repo", "title", "body", "feat", "main")

    # --- merge_pr ---

    async def test_merge_pr_success_200(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=200)
        provider = self._make_provider(client)

        result = await provider.merge_pr("https://bitbucket.org/myworkspace/myrepo/pull-requests/5")

        assert result is True
        call_url = client.post.call_args[0][0]
        assert "myworkspace/myrepo/pullrequests/5/merge" in call_url

    async def test_merge_pr_success_204(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=204)
        provider = self._make_provider(client)

        assert await provider.merge_pr("https://bitbucket.org/ws/repo/pull-requests/10") is True

    async def test_merge_pr_failure(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=409)
        provider = self._make_provider(client)

        assert await provider.merge_pr("https://bitbucket.org/ws/repo/pull-requests/3") is False

    async def test_merge_pr_parses_url_correctly(self):
        """Verify workspace/repo are extracted correctly from PR URL."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=200)
        provider = self._make_provider(client)

        await provider.merge_pr("https://bitbucket.org/acme/my-project/pull-requests/99")

        call_url = client.post.call_args[0][0]
        assert "acme/my-project/pullrequests/99/merge" in call_url

    # --- get_pr_diff ---

    async def test_get_pr_diff_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.text = "diff --git a/file.py b/file.py\n+new line"
        client.get.return_value = resp
        provider = self._make_provider(client)

        diff = await provider.get_pr_diff("ws/repo", 3)

        assert diff == "diff --git a/file.py b/file.py\n+new line"
        call_url = client.get.call_args[0][0]
        assert "ws/repo/pullrequests/3/diff" in call_url

    async def test_get_pr_diff_raises_on_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=resp
        )
        client.get.return_value = resp
        provider = self._make_provider(client)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.get_pr_diff("ws/repo", 3)

    # --- get_pr_comments ---

    async def test_get_pr_comments_single_page(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "values": [
                {"id": 1, "content": {"raw": "Looks good!"}},
                {"id": 2, "content": {"raw": "One issue here."}},
            ],
            # no "next" key → single page
        }
        client.get.return_value = resp
        provider = self._make_provider(client)

        comments = await provider.get_pr_comments("ws/repo", 5)

        assert len(comments) == 2
        assert comments[0]["body"] == "Looks good!"
        assert comments[1]["body"] == "One issue here."

    async def test_get_pr_comments_pagination(self):
        """get_pr_comments follows the 'next' link for paginated results."""
        client = AsyncMock(spec=httpx.AsyncClient)

        page1 = MagicMock()
        page1.raise_for_status = MagicMock()
        page1.json.return_value = {
            "values": [{"id": 1, "content": {"raw": "First"}}],
            "next": "https://api.bitbucket.org/2.0/repositories/ws/repo/pullrequests/5/comments?page=2",
        }

        page2 = MagicMock()
        page2.raise_for_status = MagicMock()
        page2.json.return_value = {
            "values": [{"id": 2, "content": {"raw": "Second"}}],
            # no "next" → last page
        }

        client.get.side_effect = [page1, page2]
        provider = self._make_provider(client)

        comments = await provider.get_pr_comments("ws/repo", 5)

        assert len(comments) == 2
        assert comments[0]["body"] == "First"
        assert comments[1]["body"] == "Second"
        assert client.get.call_count == 2

    async def test_get_pr_comments_empty(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"values": []}
        client.get.return_value = resp
        provider = self._make_provider(client)

        comments = await provider.get_pr_comments("ws/repo", 1)
        assert comments == []

    # --- post_pr_comment ---

    async def test_post_pr_comment_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        provider = self._make_provider(client)

        await provider.post_pr_comment("ws/repo", 7, "Great work!")

        call_url = client.post.call_args[0][0]
        assert "ws/repo/pullrequests/7/comments" in call_url
        payload = client.post.call_args[1]["json"]
        assert payload == {"content": {"raw": "Great work!"}}

    async def test_post_pr_comment_raises_on_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=resp
        )
        client.post.return_value = resp
        provider = self._make_provider(client)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.post_pr_comment("ws/repo", 7, "comment")

    # --- auth ---

    async def test_uses_bearer_auth(self):
        """Verify requests use Bearer token in headers."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=201)
        provider = self._make_provider(client)

        await provider.create_repo("ws", "repo")

        call_kwargs = client.post.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["Authorization"] == "Bearer secret"

    # --- list_issues ---

    async def test_list_issues_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "values": [
                {
                    "id": 3,
                    "title": "Fix API",
                    "content": {"raw": "Details here"},
                    "links": {"html": {"href": "https://bitbucket.org/ws/repo/issues/3"}},
                    "state": "open",
                },
            ]
        }
        client.get.return_value = resp
        provider = self._make_provider(client)
        issues = await provider.list_issues("ws/repo")
        assert len(issues) == 1
        assert issues[0]["number"] == 3
        assert issues[0]["body"] == "Details here"
        assert issues[0]["labels"] == []

    async def test_list_issues_tracker_disabled_returns_empty(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock(status_code=404)
        client.get.return_value = resp
        provider = self._make_provider(client)
        issues = await provider.list_issues("ws/repo")
        assert issues == []

    async def test_list_issues_empty_values(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"values": []}
        client.get.return_value = resp
        provider = self._make_provider(client)
        assert await provider.list_issues("ws/repo") == []


class TestFactoryBitbucket:
    def test_returns_bitbucket_provider(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("bitbucket", client)
        assert isinstance(p, BitbucketProvider)

    def test_bitbucket_not_returned_for_github(self):
        from backend.services.git import GitHubProvider

        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("github", client)
        assert isinstance(p, GitHubProvider)

    def test_bitbucket_not_returned_for_gitea(self):
        from backend.services.git import GiteaProvider

        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("gitea", client)
        assert isinstance(p, GiteaProvider)