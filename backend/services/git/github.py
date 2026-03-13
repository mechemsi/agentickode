# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""GitHub API implementation of GitProvider."""

import logging

import httpx

from backend.config import settings

logger = logging.getLogger("agentickode.git_provider")


class GitHubProvider:
    """GitHub API implementation of GitProvider."""

    _ACCEPT = "application/vnd.github+json"

    def __init__(self, client: httpx.AsyncClient, base_url: str = "", token: str = ""):
        self._client = client
        self._base_url = base_url or settings.github_api_url
        self._token = token or settings.github_token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": self._ACCEPT}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def create_repo(self, owner: str, name: str) -> bool:
        resp = await self._client.post(
            f"{self._base_url}/orgs/{owner}/repos",
            headers=self._headers(),
            json={"name": name, "auto_init": False, "private": True},
            timeout=30.0,
        )
        return resp.status_code in (201, 422)

    async def create_pr(self, repo_path: str, title: str, body: str, head: str, base: str) -> str:
        resp = await self._client.post(
            f"{self._base_url}/repos/{repo_path}/pulls",
            headers=self._headers(),
            json={"title": title, "body": body, "head": head, "base": base},
            timeout=30.0,
        )
        if resp.status_code == 422:
            errors = resp.json()
            logger.warning("GitHub 422 creating PR for %s head=%s: %s", repo_path, head, errors)
            # PR already exists — find and return it
            existing = await self._find_existing_pr(repo_path, head)
            if existing:
                logger.info("PR already exists for head=%s: %s", head, existing)
                return existing
            # Re-raise with the actual error message from GitHub
            msg = errors.get("message", resp.text)
            raise RuntimeError(f"GitHub PR creation failed: {msg}")
        resp.raise_for_status()
        return resp.json().get("html_url", "")

    async def _find_existing_pr(self, repo_path: str, head: str) -> str:
        """Find an existing open PR for the given head branch."""
        # GitHub API requires head in "owner:branch" format
        owner = repo_path.split("/")[0]
        qualified_head = f"{owner}:{head}" if ":" not in head else head
        resp = await self._client.get(
            f"{self._base_url}/repos/{repo_path}/pulls",
            headers=self._headers(),
            params={"head": qualified_head, "state": "open"},
            timeout=30.0,
        )
        if resp.status_code == 200:
            for pr in resp.json():
                if pr.get("head", {}).get("ref") == head:
                    return pr.get("html_url", "")
        return ""

    async def merge_pr(self, pr_url: str) -> bool:
        parts = pr_url.rstrip("/").split("/")
        pr_number = parts[-1]
        repo_path = "/".join(parts[-4:-2])
        resp = await self._client.put(
            f"{self._base_url}/repos/{repo_path}/pulls/{pr_number}/merge",
            headers=self._headers(),
            json={"merge_method": "merge"},
            timeout=30.0,
        )
        return resp.status_code in (200, 204)

    async def get_pr_diff(self, repo_path: str, pr_number: int) -> str:
        headers = self._headers()
        headers["Accept"] = "application/vnd.github.v3.diff"
        resp = await self._client.get(
            f"{self._base_url}/repos/{repo_path}/pulls/{pr_number}",
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.text

    async def get_pr_comments(self, repo_path: str, pr_number: int) -> list[dict]:
        resp = await self._client.get(
            f"{self._base_url}/repos/{repo_path}/pulls/{pr_number}/comments",
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def post_pr_comment(self, repo_path: str, pr_number: int, body: str) -> None:
        resp = await self._client.post(
            f"{self._base_url}/repos/{repo_path}/issues/{pr_number}/comments",
            headers=self._headers(),
            json={"body": body},
            timeout=30.0,
        )
        resp.raise_for_status()

    async def list_issues(self, repo_path: str, state: str = "open", limit: int = 30) -> list[dict]:
        resp = await self._client.get(
            f"{self._base_url}/repos/{repo_path}/issues",
            headers=self._headers(),
            params={"state": state, "per_page": limit},
            timeout=30.0,
        )
        resp.raise_for_status()
        issues = []
        for item in resp.json():
            if item.get("pull_request"):
                continue  # GitHub returns PRs in the issues endpoint
            issues.append(
                {
                    "number": item["number"],
                    "title": item.get("title", ""),
                    "body": item.get("body", "") or "",
                    "labels": [la.get("name", "") for la in item.get("labels", [])],
                    "url": item.get("html_url", ""),
                    "state": item.get("state", "open"),
                }
            )
        return issues
