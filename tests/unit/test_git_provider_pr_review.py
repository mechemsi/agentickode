# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for PR-listing and label management used by the PR-review poller."""

from unittest.mock import AsyncMock, MagicMock

import httpx

from backend.services.git import GiteaProvider, GitHubProvider


def _resp(json_value, status_code=200):
    r = MagicMock(status_code=status_code)
    r.raise_for_status = MagicMock()
    r.json.return_value = json_value
    return r


class TestGitHubPrReview:
    def _provider(self, client):
        return GitHubProvider(client, base_url="https://api.github.test", token="t")

    async def test_list_pull_requests_normalizes_fields(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _resp(
            [
                {
                    "number": 5,
                    "title": "Add x",
                    "body": "desc",
                    "labels": [{"name": "ai-review"}, {"name": "bug"}],
                    "head": {"ref": "feat", "sha": "abc123"},
                    "html_url": "https://gh/o/r/pull/5",
                    "state": "open",
                }
            ]
        )
        prs = await self._provider(client).list_pull_requests("o/r")
        assert prs == [
            {
                "number": 5,
                "title": "Add x",
                "body": "desc",
                "labels": ["ai-review", "bug"],
                "head_ref": "feat",
                "head_sha": "abc123",
                "html_url": "https://gh/o/r/pull/5",
                "state": "open",
            }
        ]
        assert "/repos/o/r/pulls" in client.get.call_args.args[0]

    async def test_add_label_posts_label_name(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _resp({})
        await self._provider(client).add_label("o/r", 5, "ai-reviewed")
        assert client.post.call_args.args[0].endswith("/repos/o/r/issues/5/labels")
        assert client.post.call_args.kwargs["json"] == {"labels": ["ai-reviewed"]}

    async def test_remove_label_deletes_by_name(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.delete.return_value = _resp({})
        await self._provider(client).remove_label("o/r", 5, "ai-review")
        assert client.delete.call_args.args[0].endswith("/repos/o/r/issues/5/labels/ai-review")


class TestGiteaPrReview:
    def _provider(self, client):
        return GiteaProvider(client, base_url="https://gitea.test", token="t")

    async def test_list_pull_requests_normalizes_fields(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _resp(
            [
                {
                    "number": 8,
                    "title": "Fix y",
                    "body": "",
                    "labels": [{"name": "ai-review"}],
                    "head": {"ref": "fix", "sha": "deadbeef"},
                    "html_url": "https://gitea.test/o/r/pulls/8",
                    "state": "open",
                }
            ]
        )
        prs = await self._provider(client).list_pull_requests("o/r")
        assert prs[0]["number"] == 8
        assert prs[0]["labels"] == ["ai-review"]
        assert prs[0]["head_sha"] == "deadbeef"
        assert prs[0]["head_ref"] == "fix"
        assert "/api/v1/repos/o/r/pulls" in client.get.call_args.args[0]

    async def test_add_label_resolves_name_to_id(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _resp(
            [{"id": 7, "name": "ai-reviewed"}, {"id": 3, "name": "ai-review"}]
        )
        client.post.return_value = _resp({})
        await self._provider(client).add_label("o/r", 8, "ai-reviewed")
        assert client.post.call_args.kwargs["json"] == {"labels": [7]}
        assert client.post.call_args.args[0].endswith("/api/v1/repos/o/r/issues/8/labels")

    async def test_remove_label_deletes_by_resolved_id(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _resp([{"id": 3, "name": "ai-review"}])
        client.delete.return_value = _resp({})
        await self._provider(client).remove_label("o/r", 8, "ai-review")
        assert client.delete.call_args.args[0].endswith("/api/v1/repos/o/r/issues/8/labels/3")

    async def test_add_label_unknown_name_is_noop(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _resp([{"id": 3, "name": "something-else"}])
        await self._provider(client).add_label("o/r", 8, "ai-reviewed")
        client.post.assert_not_called()  # nothing to add — label doesn't exist

    async def test_label_lookup_paginates(self):
        """A label beyond the first 100 still resolves (Gitea labels API paginates)."""
        client = AsyncMock(spec=httpx.AsyncClient)
        page1 = _resp([{"id": i, "name": f"l{i}"} for i in range(100)])
        page2 = _resp([{"id": 777, "name": "ai-reviewed"}])
        client.get.side_effect = [page1, page2]
        client.post.return_value = _resp({})
        await self._provider(client).add_label("o/r", 8, "ai-reviewed")
        assert client.get.call_count == 2
        assert client.post.call_args.kwargs["json"] == {"labels": [777]}
