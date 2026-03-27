# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Plane TaskManager — bidirectional issue status sync via state groups."""

import logging

import httpx

logger = logging.getLogger("agentickode.task_management.plane")

# Plane state group mapping
_STATUS_STATE_GROUP = {
    "in_progress": "started",
    "done": "completed",
    "failed": "cancelled",
}


class PlaneTaskManager:
    def __init__(self, client: httpx.AsyncClient, api_url: str, api_key: str):
        self._client = client
        self._api_url = api_url.rstrip("/")
        self._headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    async def update_status(self, meta: dict, status: str) -> None:
        """Update Plane issue state group."""
        workspace_slug = meta.get("workspace_slug", "")
        project_id = meta.get("project_id") or meta.get("plane_project_id", "")
        issue_id = meta.get("issue_id") or meta.get("id", "")
        if not all([workspace_slug, project_id, issue_id]):
            return

        state_group = _STATUS_STATE_GROUP.get(status)
        if not state_group:
            return

        url = (
            f"{self._api_url}/api/v1/workspaces/{workspace_slug}"
            f"/projects/{project_id}/issues/{issue_id}/"
        )
        resp = await self._client.patch(
            url, headers=self._headers, json={"state_group": state_group}
        )
        if resp.status_code not in (200, 204):
            logger.warning("Failed to update Plane issue %s: %s", issue_id, resp.status_code)
        else:
            logger.info("Plane issue %s → %s", issue_id, state_group)

    async def add_comment(self, meta: dict, body: str) -> None:
        """Post a comment on a Plane issue."""
        workspace_slug = meta.get("workspace_slug", "")
        project_id = meta.get("project_id") or meta.get("plane_project_id", "")
        issue_id = meta.get("issue_id") or meta.get("id", "")
        if not all([workspace_slug, project_id, issue_id]):
            return

        url = (
            f"{self._api_url}/api/v1/workspaces/{workspace_slug}"
            f"/projects/{project_id}/issues/{issue_id}/comments/"
        )
        await self._client.post(url, headers=self._headers, json={"comment_html": body})

    async def create_issue(
        self, project_ref: str, title: str, body: str, labels: list[str] | None = None
    ) -> dict:
        """Create a Plane issue. project_ref = 'workspace_slug/project_id'."""
        parts = project_ref.split("/", 1)
        if len(parts) != 2:
            return {"id": "", "url": ""}
        workspace_slug, project_id = parts

        url = (
            f"{self._api_url}/api/v1/workspaces/{workspace_slug}" f"/projects/{project_id}/issues/"
        )
        payload: dict = {"name": title, "description_html": body}
        resp = await self._client.post(url, headers=self._headers, json=payload)
        data = resp.json()
        return {"id": data.get("id", ""), "url": data.get("url", "")}
