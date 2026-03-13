# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Bitbucket Cloud REST API v2.0 implementation of GitProvider.

Uses workspace/repository access tokens with Bearer authentication.
"""

import httpx

from backend.config import settings


class BitbucketProvider:
    """Bitbucket Cloud REST API v2.0 implementation of GitProvider."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "",
        access_token: str = "",
    ):
        self._client = client
        self._base_url = (base_url or settings.bitbucket_base_url).rstrip("/") + "/2.0"
        self._token = access_token or settings.bitbucket_access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def create_repo(self, owner: str, name: str) -> bool:
        resp = await self._client.post(
            f"{self._base_url}/repositories/{owner}/{name}",
            headers=self._headers(),
            json={"scm": "git", "is_private": True},
            timeout=30.0,
        )
        return resp.status_code in (200, 201, 409)

    async def create_pr(self, repo_path: str, title: str, body: str, head: str, base: str) -> str:
        resp = await self._client.post(
            f"{self._base_url}/repositories/{repo_path}/pullrequests",
            headers=self._headers(),
            json={
                "title": title,
                "description": body,
                "source": {"branch": {"name": head}},
                "destination": {"branch": {"name": base}},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json().get("links", {}).get("html", {}).get("href", "")

    async def merge_pr(self, pr_url: str) -> bool:
        # URL format: https://bitbucket.org/{workspace}/{repo_slug}/pull-requests/{id}
        parts = pr_url.rstrip("/").split("/")
        pr_id = parts[-1]
        workspace = parts[-4]
        repo_slug = parts[-3]
        resp = await self._client.post(
            f"{self._base_url}/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/merge",
            headers=self._headers(),
            timeout=30.0,
        )
        return resp.status_code in (200, 204)

    async def get_pr_diff(self, repo_path: str, pr_number: int) -> str:
        resp = await self._client.get(
            f"{self._base_url}/repositories/{repo_path}/pullrequests/{pr_number}/diff",
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.text

    async def get_pr_comments(self, repo_path: str, pr_number: int) -> list[dict]:
        comments: list[dict] = []
        url: str | None = (
            f"{self._base_url}/repositories/{repo_path}/pullrequests/{pr_number}/comments"
        )
        while url:
            resp = await self._client.get(url, headers=self._headers(), timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("values", []):
                comments.append({"body": item.get("content", {}).get("raw", ""), **item})
            url = data.get("next")
        return comments

    async def post_pr_comment(self, repo_path: str, pr_number: int, body: str) -> None:
        resp = await self._client.post(
            f"{self._base_url}/repositories/{repo_path}/pullrequests/{pr_number}/comments",
            headers=self._headers(),
            json={"content": {"raw": body}},
            timeout=30.0,
        )
        resp.raise_for_status()

    async def list_issues(self, repo_path: str, state: str = "open", limit: int = 30) -> list[dict]:
        resp = await self._client.get(
            f"{self._base_url}/repositories/{repo_path}/issues",
            headers=self._headers(),
            params={"state": state, "pagelen": limit},
            timeout=30.0,
        )
        if resp.status_code == 404:
            return []  # Issue tracker not enabled
        resp.raise_for_status()
        return [
            {
                "number": item["id"],
                "title": item.get("title", ""),
                "body": item.get("content", {}).get("raw", "") or "",
                "labels": [],
                "url": item.get("links", {}).get("html", {}).get("href", ""),
                "state": item.get("state", "open"),
            }
            for item in resp.json().get("values", [])
        ]
