# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""GitLab API v4 implementation of GitProvider."""

import logging
from urllib.parse import quote

import httpx

from backend.config import settings

logger = logging.getLogger("agentickode.git_provider")


class GitLabProvider:
    """GitLab REST API v4 implementation of GitProvider."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "", token: str = ""):
        self._client = client
        self._base_url = base_url or settings.gitlab_api_url
        self._token = token or settings.gitlab_token

    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"PRIVATE-TOKEN": self._token}
        return {}

    def _encode_path(self, repo_path: str) -> str:
        """URL-encode a 'owner/repo' path for GitLab API URLs."""
        return quote(repo_path, safe="")

    async def create_repo(self, owner: str, name: str) -> bool:
        resp = await self._client.post(
            f"{self._base_url}/api/v4/projects",
            headers=self._headers(),
            json={"path": name, "namespace_path": owner, "visibility": "private"},
            timeout=30.0,
        )
        return resp.status_code in (200, 201, 400, 409)

    async def create_pr(self, repo_path: str, title: str, body: str, head: str, base: str) -> str:
        encoded = self._encode_path(repo_path)
        resp = await self._client.post(
            f"{self._base_url}/api/v4/projects/{encoded}/merge_requests",
            headers=self._headers(),
            json={
                "title": title,
                "description": body,
                "source_branch": head,
                "target_branch": base,
            },
            timeout=30.0,
        )
        if resp.status_code in (409, 422):
            existing = await self._find_existing_mr(repo_path, head)
            if existing:
                logger.info("MR already exists for head=%s: %s", head, existing)
                return existing
        resp.raise_for_status()
        return resp.json().get("web_url", "")

    async def _find_existing_mr(self, repo_path: str, source_branch: str) -> str:
        """Find an existing open MR for the given source branch."""
        encoded = self._encode_path(repo_path)
        resp = await self._client.get(
            f"{self._base_url}/api/v4/projects/{encoded}/merge_requests",
            headers=self._headers(),
            params={"state": "opened", "source_branch": source_branch},
            timeout=30.0,
        )
        if resp.status_code == 200:
            for mr in resp.json():
                if mr.get("source_branch") == source_branch:
                    return mr.get("web_url", "")
        return ""

    async def merge_pr(self, pr_url: str) -> bool:
        # URL format: https://gitlab.com/{owner}/{repo}/-/merge_requests/{iid}
        parts = pr_url.rstrip("/").split("/")
        iid = parts[-1]
        # owner/repo is parts[-5] and parts[-4]; /-/ is parts[-3]; merge_requests parts[-2]
        repo_path = "/".join(parts[-5:-3])
        encoded = self._encode_path(repo_path)
        resp = await self._client.put(
            f"{self._base_url}/api/v4/projects/{encoded}/merge_requests/{iid}/merge",
            headers=self._headers(),
            timeout=30.0,
        )
        return resp.status_code in (200, 204)

    async def get_pr_diff(self, repo_path: str, pr_number: int) -> str:
        encoded = self._encode_path(repo_path)
        resp = await self._client.get(
            f"{self._base_url}/api/v4/projects/{encoded}/merge_requests/{pr_number}/changes",
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        diffs = data.get("changes", [])
        return "\n".join(c.get("diff", "") for c in diffs)

    async def get_pr_comments(self, repo_path: str, pr_number: int) -> list[dict]:
        encoded = self._encode_path(repo_path)
        resp = await self._client.get(
            f"{self._base_url}/api/v4/projects/{encoded}/merge_requests/{pr_number}/notes",
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def post_pr_comment(self, repo_path: str, pr_number: int, body: str) -> None:
        encoded = self._encode_path(repo_path)
        resp = await self._client.post(
            f"{self._base_url}/api/v4/projects/{encoded}/merge_requests/{pr_number}/notes",
            headers=self._headers(),
            json={"body": body},
            timeout=30.0,
        )
        resp.raise_for_status()

    async def list_issues(self, repo_path: str, state: str = "open", limit: int = 30) -> list[dict]:
        encoded = self._encode_path(repo_path)
        gl_state = "opened" if state == "open" else state
        resp = await self._client.get(
            f"{self._base_url}/api/v4/projects/{encoded}/issues",
            headers=self._headers(),
            params={"state": gl_state, "per_page": limit},
            timeout=30.0,
        )
        resp.raise_for_status()
        return [
            {
                "number": item["iid"],
                "title": item.get("title", ""),
                "body": item.get("description", "") or "",
                "labels": item.get("labels", []),
                "url": item.get("web_url", ""),
                "state": "open" if item.get("state") == "opened" else item.get("state", ""),
            }
            for item in resp.json()
        ]
