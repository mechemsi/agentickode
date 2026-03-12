# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for GitLabProvider — GitLab REST API v4 implementation."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.services.git import GitLabProvider, get_git_provider


class TestGitLabProvider:
    def _make_provider(self, client=None):
        client = client or AsyncMock(spec=httpx.AsyncClient)
        return GitLabProvider(
            client,
            base_url="https://gitlab.com",
            token="glpat-secret",
        )

    # --- create_repo ---

    async def test_create_repo_success_201(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=201)
        provider = self._make_provider(client)
        assert await provider.create_repo("mygroup", "myrepo") is True
        client.post.assert_called_once()
        call_kwargs = client.post.call_args
        assert "/api/v4/projects" in call_kwargs[0][0]
        payload = call_kwargs[1]["json"]
        assert payload["path"] == "myrepo"

    async def test_create_repo_already_exists_400(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=400)
        provider = self._make_provider(client)
        assert await provider.create_repo("mygroup", "myrepo") is True

    async def test_create_repo_already_exists_409(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=409)
        provider = self._make_provider(client)
        assert await provider.create_repo("mygroup", "myrepo") is True

    async def test_create_repo_failure_500(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=500)
        provider = self._make_provider(client)
        assert await provider.create_repo("mygroup", "myrepo") is False

    # --- create_pr ---

    async def test_create_pr_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 201
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"web_url": "https://gitlab.com/mygroup/myrepo/-/merge_requests/3"}
        client.post.return_value = resp
        provider = self._make_provider(client)

        url = await provider.create_pr("mygroup/myrepo", "My MR", "Description", "feature", "main")

        assert url == "https://gitlab.com/mygroup/myrepo/-/merge_requests/3"
        call_args = client.post.call_args
        # Repo path must be URL-encoded in the request URL
        assert "mygroup%2Fmyrepo" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["title"] == "My MR"
        assert payload["description"] == "Description"
        assert payload["source_branch"] == "feature"
        assert payload["target_branch"] == "main"

    async def test_create_pr_duplicate_409_returns_existing(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        # POST returns 409 (duplicate MR)
        post_resp = MagicMock(status_code=409)
        client.post.return_value = post_resp
        # GET returns list with existing MR
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = [
            {
                "source_branch": "feature",
                "web_url": "https://gitlab.com/mygroup/myrepo/-/merge_requests/7",
            }
        ]
        client.get.return_value = get_resp
        provider = self._make_provider(client)

        url = await provider.create_pr("mygroup/myrepo", "title", "body", "feature", "main")

        assert url == "https://gitlab.com/mygroup/myrepo/-/merge_requests/7"

    async def test_create_pr_duplicate_422_returns_existing(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        post_resp = MagicMock(status_code=422)
        client.post.return_value = post_resp
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = [
            {
                "source_branch": "feature",
                "web_url": "https://gitlab.com/grp/repo/-/merge_requests/99",
            }
        ]
        client.get.return_value = get_resp
        provider = self._make_provider(client)

        url = await provider.create_pr("grp/repo", "title", "body", "feature", "main")
        assert url == "https://gitlab.com/grp/repo/-/merge_requests/99"

    async def test_create_pr_raises_on_other_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 500
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=resp
        )
        client.post.return_value = resp
        provider = self._make_provider(client)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.create_pr("grp/repo", "title", "body", "feat", "main")

    # --- merge_pr ---

    async def test_merge_pr_success_200(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.put.return_value = MagicMock(status_code=200)
        provider = self._make_provider(client)

        result = await provider.merge_pr("https://gitlab.com/mygroup/myrepo/-/merge_requests/5")

        assert result is True
        call_url = client.put.call_args[0][0]
        assert "mygroup%2Fmyrepo" in call_url
        assert "merge_requests/5/merge" in call_url

    async def test_merge_pr_success_204(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.put.return_value = MagicMock(status_code=204)
        provider = self._make_provider(client)

        assert (
            await provider.merge_pr("https://gitlab.com/mygroup/myrepo/-/merge_requests/10") is True
        )

    async def test_merge_pr_failure(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.put.return_value = MagicMock(status_code=405)
        provider = self._make_provider(client)

        assert (
            await provider.merge_pr("https://gitlab.com/mygroup/myrepo/-/merge_requests/3") is False
        )

    # --- get_pr_diff ---

    async def test_get_pr_diff_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "changes": [
                {"diff": "diff --git a/file.py b/file.py\n+new line"},
                {"diff": "+another line"},
            ]
        }
        client.get.return_value = resp
        provider = self._make_provider(client)

        diff = await provider.get_pr_diff("mygroup/myrepo", 3)

        assert "diff --git a/file.py b/file.py" in diff
        assert "+another line" in diff
        call_url = client.get.call_args[0][0]
        assert "mygroup%2Fmyrepo" in call_url
        assert "merge_requests/3/changes" in call_url

    async def test_get_pr_diff_raises_on_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=resp
        )
        client.get.return_value = resp
        provider = self._make_provider(client)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.get_pr_diff("mygroup/myrepo", 3)

    # --- get_pr_comments ---

    async def test_get_pr_comments_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {"id": 1, "body": "Looks good!"},
            {"id": 2, "body": "One issue here."},
        ]
        client.get.return_value = resp
        provider = self._make_provider(client)

        comments = await provider.get_pr_comments("mygroup/myrepo", 5)

        assert len(comments) == 2
        assert comments[0]["body"] == "Looks good!"
        assert comments[1]["body"] == "One issue here."
        call_url = client.get.call_args[0][0]
        assert "mygroup%2Fmyrepo" in call_url
        assert "merge_requests/5/notes" in call_url

    async def test_get_pr_comments_empty(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = []
        client.get.return_value = resp
        provider = self._make_provider(client)

        comments = await provider.get_pr_comments("mygroup/myrepo", 1)
        assert comments == []

    async def test_get_pr_comments_raises_on_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=resp
        )
        client.get.return_value = resp
        provider = self._make_provider(client)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.get_pr_comments("mygroup/myrepo", 5)

    # --- post_pr_comment ---

    async def test_post_pr_comment_success(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp
        provider = self._make_provider(client)

        await provider.post_pr_comment("mygroup/myrepo", 7, "Great work!")

        call_url = client.post.call_args[0][0]
        assert "mygroup%2Fmyrepo" in call_url
        assert "merge_requests/7/notes" in call_url
        payload = client.post.call_args[1]["json"]
        assert payload == {"body": "Great work!"}

    async def test_post_pr_comment_raises_on_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=resp
        )
        client.post.return_value = resp
        provider = self._make_provider(client)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.post_pr_comment("mygroup/myrepo", 7, "comment")

    # --- auth headers ---

    async def test_uses_private_token_header(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = MagicMock(status_code=201)
        provider = self._make_provider(client)

        await provider.create_repo("grp", "repo")

        call_kwargs = client.post.call_args[1]
        assert call_kwargs["headers"]["PRIVATE-TOKEN"] == "glpat-secret"

    # --- url encoding ---

    async def test_repo_path_is_url_encoded(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 201
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"web_url": "https://gitlab.com/org/repo/-/merge_requests/1"}
        client.post.return_value = resp
        provider = self._make_provider(client)

        await provider.create_pr("org/repo", "title", "body", "feat", "main")

        call_url = client.post.call_args[0][0]
        assert "org%2Frepo" in call_url
        assert "org/repo" not in call_url.split("/api/v4/projects/")[1]

    # --- list_issues ---

    async def test_list_issues_normalizes_gitlab_fields(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {
                "iid": 5,
                "title": "Fix CSS",
                "description": "The CSS is broken",
                "labels": ["frontend"],
                "web_url": "https://gitlab.com/grp/repo/-/issues/5",
                "state": "opened",
            },
        ]
        client.get.return_value = resp
        provider = self._make_provider(client)
        issues = await provider.list_issues("grp/repo")
        assert len(issues) == 1
        assert issues[0]["number"] == 5
        assert issues[0]["body"] == "The CSS is broken"
        assert issues[0]["state"] == "open"  # normalized from "opened"
        assert issues[0]["labels"] == ["frontend"]

    async def test_list_issues_maps_state_opened_to_open(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = []
        client.get.return_value = resp
        provider = self._make_provider(client)
        await provider.list_issues("grp/repo")
        params = client.get.call_args[1]["params"]
        assert params["state"] == "opened"

    async def test_list_issues_url_encodes_path(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = []
        client.get.return_value = resp
        provider = self._make_provider(client)
        await provider.list_issues("grp/repo")
        call_url = client.get.call_args[0][0]
        assert "grp%2Frepo" in call_url


class TestFactoryGitLab:
    def test_returns_gitlab_provider(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("gitlab", client)
        assert isinstance(p, GitLabProvider)

    def test_gitlab_not_returned_for_github(self):
        from backend.services.git import GitHubProvider

        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("github", client)
        assert isinstance(p, GitHubProvider)

    def test_gitlab_not_returned_for_gitea(self):
        from backend.services.git import GiteaProvider

        client = AsyncMock(spec=httpx.AsyncClient)
        p = get_git_provider("gitea", client)
        assert isinstance(p, GiteaProvider)