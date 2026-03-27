# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""GitHub TaskManager — bidirectional issue status sync via labels and comments."""

import logging

import httpx

logger = logging.getLogger("agentickode.task_management.github")

# Label-based status mapping
_STATUS_LABELS = {
    "in_progress": "ai-in-progress",
    "done": "ai-done",
    "failed": "ai-failed",
}
_ALL_STATUS_LABELS = set(_STATUS_LABELS.values())


class GitHubTaskManager:
    def __init__(
        self, client: httpx.AsyncClient, token: str, api_url: str = "https://api.github.com"
    ):
        self._client = client
        self._token = token
        self._api_url = api_url.rstrip("/")
        self._headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    async def update_status(self, meta: dict, status: str) -> None:
        """Add/remove status labels on the GitHub issue."""
        repo = meta.get("repo_full_name", "")
        issue_number = meta.get("issue_number")
        if not repo or not issue_number:
            return

        new_label = _STATUS_LABELS.get(status)
        if not new_label:
            return

        # Get current labels
        url = f"{self._api_url}/repos/{repo}/issues/{issue_number}/labels"
        resp = await self._client.get(url, headers=self._headers)
        if resp.status_code != 200:
            logger.warning(
                "Failed to get labels for %s#%s: %s", repo, issue_number, resp.status_code
            )
            return

        current_labels = {lbl["name"] for lbl in resp.json()}

        # Remove old status labels, add new one
        for old_label in _ALL_STATUS_LABELS & current_labels:
            await self._client.delete(f"{url}/{old_label}", headers=self._headers)

        await self._client.post(url, headers=self._headers, json={"labels": [new_label]})
        logger.info("GitHub %s#%s → label %s", repo, issue_number, new_label)

    async def add_comment(self, meta: dict, body: str) -> None:
        """Post a comment on the GitHub issue."""
        repo = meta.get("repo_full_name", "")
        issue_number = meta.get("issue_number")
        if not repo or not issue_number:
            return

        url = f"{self._api_url}/repos/{repo}/issues/{issue_number}/comments"
        resp = await self._client.post(url, headers=self._headers, json={"body": body})
        if resp.status_code not in (200, 201):
            logger.warning("Failed to comment on %s#%s: %s", repo, issue_number, resp.status_code)

    async def create_issue(
        self, project_ref: str, title: str, body: str, labels: list[str] | None = None
    ) -> dict:
        """Create a new GitHub issue."""
        url = f"{self._api_url}/repos/{project_ref}/issues"
        payload: dict = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        resp = await self._client.post(url, headers=self._headers, json=payload)
        data = resp.json()
        return {"id": data.get("number"), "url": data.get("html_url", "")}
